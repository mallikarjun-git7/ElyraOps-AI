"""Opt-in local API-token access control for ElyraOps HTTP endpoints.

NOT a production identity system: no OIDC, MFA, managed key rotation, sessions,
PostgreSQL RLS, or authenticated end users behind the browser. Designed for a
local-only defense-in-depth demonstration, not for internet exposure.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass

ROLES = frozenset({'viewer', 'analyst', 'approver', 'admin'})
PERMISSIONS = {
    'viewer': frozenset({'read'}),
    'analyst': frozenset({'read', 'create', 'investigate'}),
    'approver': frozenset({'read', 'decide'}),
    'admin': frozenset({'read', 'create', 'investigate', 'decide'}),
}


class SecurityError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Principal:
    name: str
    organization: str
    role: str


def enabled() -> bool:
    mode = os.environ.get('ELYRA_SECURITY_MODE', 'disabled').strip().lower()
    if mode not in {'disabled', 'required'}:
        raise SecurityError(503, 'Security mode is misconfigured')
    return mode == 'required'


def _users() -> dict:
    raw = os.environ.get('ELYRA_ACCESS_TOKENS_JSON', '').strip()
    if not raw:
        raise SecurityError(503, 'Security tokens are not configured')
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or not data:
            raise ValueError('invalid principal map')
        for digest, user in data.items():
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('invalid digest')
            if (not isinstance(user, dict) or user.get('role') not in ROLES
                or not isinstance(user.get('organization'), str) or not 1 <= len(user['organization']) <= 100
                or not isinstance(user.get('name'), str) or not 1 <= len(user['name']) <= 80):
                raise ValueError('invalid principal')
        return data
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise SecurityError(503, 'Security token configuration is invalid') from exc


def authenticate(authorization_header: str | None) -> Principal | None:
    if not enabled():
        return None
    users = _users()  # Fail closed when required and config is missing or malformed.
    if not authorization_header or not authorization_header.startswith('Bearer '):
        raise SecurityError(401, 'Bearer token required')
    token = authorization_header[7:]
    if not 32 <= len(token) <= 512 or any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise SecurityError(401, 'Invalid bearer token')
    digest = hashlib.sha256(token.encode('utf-8')).hexdigest()
    matched = None
    for expected, user in users.items():
        if hmac.compare_digest(digest, expected):
            matched = user
    if matched is None:
        raise SecurityError(401, 'Invalid bearer token')
    return Principal(matched['name'], matched['organization'], matched['role'])


def authorize(principal: Principal | None, action: str, organization: str | None = None) -> None:
    if not enabled():
        return
    if principal is None:
        raise SecurityError(401, 'Authentication required')
    if action not in PERMISSIONS[principal.role]:
        raise SecurityError(403, 'Role is not permitted')
    if organization is not None and not hmac.compare_digest(principal.organization, organization):
        # Hide whether resources in another organization exist.
        raise SecurityError(404, 'Case not found')


def internal_token_valid(provided: str | None) -> bool:
    expected = os.environ.get('ELYRA_AGENT_TOKEN', '')
    if enabled():
        if len(expected) < 32:
            raise SecurityError(503, 'Internal service token must be at least 32 characters')
        return bool(provided) and hmac.compare_digest(provided, expected)
    return not expected or (bool(provided) and hmac.compare_digest(provided, expected))
