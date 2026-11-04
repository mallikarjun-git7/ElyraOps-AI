"""Zero-dependency local HTTP app. For local/demo use only; add real auth before production."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import core
from . import agent_client
from . import security
from . import pg_cases
from . import observability as obs

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

class Handler(BaseHTTPRequestHandler):
    server_version = "ElyraOpsDemo/0.1"

    def log_message(self, fmt, *args):
        # The default BaseHTTPRequestHandler logs raw request paths, including query strings.
        # JSON request summaries from obs.finish_http_request are privacy-bounded.
        pass

    def send_response(self, code, message=None):
        self._response_status = code
        return super().send_response(code, message)

    def end_headers(self):
        if getattr(self, "_request_id", None):
            self.send_header("X-Request-ID", self._request_id)
        return super().end_headers()

    def _observed(self, method, handler):
        rid = obs.normalize_request_id(self.headers.get("X-Request-ID"))
        self._request_id = rid
        self._response_status = 500
        started = time.perf_counter()
        with obs.request_context(rid):
            try:
                return handler()
            finally:
                path = urlparse(self.path).path
                obs.finish_http_request("dashboard", method, path, self._response_status, started, rid)


    def write_json(self, data, status=200):
        output = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(output)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(output)

    def read_json(self):
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise ValueError("Content-Type must be application/json")
        size = int(self.headers.get("Content-Length", "0"))
        if size < 1 or size > 16384:
            raise ValueError("Request body must be 1–16384 bytes")
        return json.loads(self.rfile.read(size))

    def do_GET(self):
        return self._observed("GET", self._safe_GET)

    def _safe_GET(self):
        try:
            return self._do_GET()
        except pg_cases.CaseStoreUnavailable:
            return self.write_json({"error": "PostgreSQL case store unavailable"}, 503)

    def _do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/health":
            return self.write_json({"status": "ok", "service": "elyraops-demo", "mode": "agent-service" if os.environ.get("ELYRA_AGENT_URL") else "simulation"})
        if path == "/metrics":
            try:
                allowed = security.internal_token_valid(self.headers.get("X-Agent-Token"))
            except security.SecurityError as exc:
                return self.write_json({"error":"Metrics access unavailable"}, exc.status)
            if not allowed:
                return self.write_json({"error":"Internal service token required"}, 401)
            output = obs.metrics_text("dashboard").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(output)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(output)
        if path == "/api/auth/config":
            try:
                return self.write_json({"enabled": security.enabled()})
            except security.SecurityError as exc:
                return self.write_json({"error": str(exc)}, exc.status)
        if path.startswith("/api/"):
            try:
                principal = security.authenticate(self.headers.get("Authorization"))
                security.authorize(principal, "read")
            except security.SecurityError as exc:
                return self.write_json({"error": str(exc)}, exc.status)
            organization = principal.organization if principal else None
        else:
            principal = None
            organization = None
        if path == "/api/auth/me":
            return self.write_json({"enabled": bool(principal), "name": principal.name if principal else "Demo operator", "role": principal.role if principal else "demo", "organization": organization})
        if path == "/api/dashboard":
            return self.write_json(core.dashboard(organization))
        if path == "/api/cases":
            return self.write_json({"items": core.list_cases(organization)})
        if path == "/api/knowledge":
            return self.write_json({"items": core.knowledge()})
        match = re.fullmatch(r"/api/cases/(EC-[A-Za-z0-9-]+)", path)
        if match:
            case = core.get_case(match.group(1), organization)
            return self.write_json(case) if case else self.write_json({"error": "Case not found"}, 404)
        if path == "/":
            path = "/index.html"
        if path not in {"/index.html", "/app.js", "/styles.css"}:
            return self.write_json({"error": "Not found"}, 404)
        file_path = WEB / path.lstrip("/")
        if not file_path.exists():
            return self.write_json({"error": "Not found"}, 404)
        data = file_path.read_bytes()
        mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith("text/") or "javascript" in mime else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        return self._observed("POST", self._do_POST)

    def _do_POST(self):
        path = unquote(urlparse(self.path).path)
        try:
            principal = security.authenticate(self.headers.get("Authorization"))
            payload = self.read_json()
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            if path == "/api/cases":
                security.authorize(principal, "create")
                return self.write_json(core.create_case(payload, principal.organization if principal else None), 201)
            match = re.fullmatch(r"/api/cases/(EC-[A-Za-z0-9-]+)/(investigate|decision)", path)
            if match:
                case_id, operation = match.groups()
                organization = principal.organization if principal else None
                if operation == "investigate":
                    security.authorize(principal, "investigate")
                    if not core.get_case(case_id, organization):
                        return self.write_json({"error": "Case not found"}, 404)
                    return self.write_json(agent_client.investigate(case_id, organization) if os.environ.get("ELYRA_AGENT_URL") else core.investigate(case_id, organization))
                security.authorize(principal, "decide")
                return self.write_json(core.decide(case_id, payload.get("decision"), principal.name if principal else payload.get("actor"), organization))
            return self.write_json({"error": "Not found"}, 404)
        except security.SecurityError as exc:
            return self.write_json({"error": str(exc)}, exc.status)
        except pg_cases.CaseStoreUnavailable:
            return self.write_json({"error": "PostgreSQL case store unavailable"}, 503)
        except agent_client.AgentUnavailable as exc:
            return self.write_json({"error": str(exc)}, 502)
        except KeyError:
            return self.write_json({"error": "Case not found"}, 404)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self.write_json({"error": str(exc)}, 400)


def validate_local_listener(host: str) -> None:
    """Only the explicitly opted-in Docker Compose bridge may listen on all interfaces.

    Compose must publish the dashboard to the HOST loopback interface only.
    The container listener itself cannot verify Docker's host port binding.
    """
    compose_mode = os.environ.get("ELYRA_LOCAL_COMPOSE", "") == "1"
    guarded = security.enabled()
    if compose_mode:
        if host != "0.0.0.0" or not guarded:
            raise RuntimeError("Local Compose mode needs guarded authentication and container binding")
        if not os.environ.get("ELYRA_CASES_DATABASE_URL", "").strip():
            raise RuntimeError("Local Compose mode requires the PostgreSQL case backend")
        if os.environ.get("ELYRA_RAG_RLS_MODE", "") != "required":
            raise RuntimeError("Local Compose mode requires secure RAG RLS")
        return
    if guarded and host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("Guarded demo must bind to localhost; public exposure is unsupported")


def run():
    host = os.environ.get("HOST", "127.0.0.1")
    validate_local_listener(host)  # Validate before binding the socket.
    core.initialize()
    port = int(os.environ.get("PORT", "8080"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    mode = "AGENT SERVICE" if os.environ.get("ELYRA_AGENT_URL") else "SIMULATION MODE"
    security_mode = "GUARDED LOCAL API" if security.enabled() else "UNGUARDED DEMO"
    print(f"ElyraOps AI demo at http://{host}:{port} | {mode} | {security_mode}", flush=True)
    httpd.serve_forever()

if __name__ == "__main__":
    run()
