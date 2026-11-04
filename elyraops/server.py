"""Zero-dependency local HTTP app. For local/demo use only; add real auth before production."""
from __future__ import annotations

import json
import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import core

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

class Handler(BaseHTTPRequestHandler):
    server_version = "ElyraOpsDemo/0.1"

    def log_message(self, fmt, *args):
        super().log_message(fmt, *args)

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
        path = unquote(urlparse(self.path).path)
        if path == "/health":
            return self.write_json({"status": "ok", "service": "elyraops-demo", "mode": "simulation"})
        if path == "/api/dashboard":
            return self.write_json(core.dashboard())
        if path == "/api/cases":
            return self.write_json({"items": core.list_cases()})
        if path == "/api/knowledge":
            return self.write_json({"items": core.knowledge()})
        match = re.fullmatch(r"/api/cases/(EC-[A-Za-z0-9-]+)", path)
        if match:
            case = core.get_case(match.group(1))
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
        path = unquote(urlparse(self.path).path)
        try:
            payload = self.read_json()
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            if path == "/api/cases":
                return self.write_json(core.create_case(payload), 201)
            match = re.fullmatch(r"/api/cases/(EC-[A-Za-z0-9-]+)/(investigate|decision)", path)
            if match:
                case_id, operation = match.groups()
                if operation == "investigate":
                    return self.write_json(core.investigate(case_id))
                return self.write_json(core.decide(case_id, payload.get("decision"), payload.get("actor")))
            return self.write_json({"error": "Not found"}, 404)
        except KeyError:
            return self.write_json({"error": "Case not found"}, 404)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self.write_json({"error": str(exc)}, 400)


def run():
    core.initialize()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"ElyraOps AI demo at http://{host}:{port} | SIMULATION MODE | No authentication", flush=True)
    httpd.serve_forever()

if __name__ == "__main__":
    run()
