"""Generate local-only hashed bearer-token config for a single synthetic tenant."""
import argparse
import hashlib
import json
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--organization', default='Synthetic Organization', help='Demo tenant label')
args = parser.parse_args()
org = args.organization.strip()
if not 1 <= len(org) <= 100 or any(c in org for c in "\r\n'\""):
    parser.error('Organization must be 1-100 characters without quotes or line breaks')
path = Path('.env.security')
if path.exists():
    parser.error('.env.security already exists; refusing to overwrite existing credentials')
principals = {}
tokens = {}
for role in ('viewer', 'analyst', 'approver', 'admin'):
    token = secrets.token_urlsafe(36)
    tokens[role] = token
    principals[hashlib.sha256(token.encode()).hexdigest()] = {
        'role': role, 'name': 'Demo ' + role.title(), 'organization': org,
    }
internal = secrets.token_urlsafe(40)
content = (
    "export ELYRA_SECURITY_MODE='required'\n"
    + "export ELYRA_ACCESS_TOKENS_JSON='" + json.dumps(principals, separators=(',', ':')) + "'\n"
    + "export ELYRA_AGENT_TOKEN='" + internal + "'\n"
)
with path.open('x') as f:
    f.write(content)
path.chmod(0o600)
print('Created .env.security (mode 0600). Keep this file local and secret.\n')
for role, token in tokens.items():
    print(f'{role.upper()} TOKEN: {token}')
print('\nTokens are shown once. Copy them to a password manager; never commit or share them.')
