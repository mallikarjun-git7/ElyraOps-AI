"""Dependency-free, read-only HTTP smoke tests for container or CI deployments."""
from __future__ import annotations

import argparse
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


def validate_url(url: str):
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname not in
            {"127.0.0.1", "localhost", "elyra-agent", "elyra-dashboard"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"} or parsed.port is None):
        raise ValueError("Smoke test targets must be trusted local/Compose HTTP origins")


def get_json(url: str, timeout: float = 6):
    with urlopen(url, timeout=timeout) as response:
        body = response.read(16_384)
        if response.status != 200 or not response.headers.get("X-Request-ID"):
            raise RuntimeError("Unexpected status or missing correlation ID")
    return json.loads(body)


def run(dashboard_url: str, agent_url: str, guard: bool = False, attempts: int = 20, delay: float = 2.0):
    validate_url(dashboard_url)
    validate_url(agent_url)
    errors = []
    for _ in range(attempts):
        try:
            dashboard = get_json(dashboard_url + "/health")
            agent = get_json(agent_url + "/health")
            ready = get_json(agent_url + "/ready")
            if dashboard.get("status") != "ok" or agent.get("status") != "ok" or ready.get("status") != "ready":
                raise RuntimeError("An expected liveness/readiness field is missing")
            if guard:
                auth = get_json(dashboard_url + "/api/auth/config")
                if auth.get("enabled") is not True:
                    raise RuntimeError("Authentication is not required")
                try:
                    get_json(dashboard_url + "/api/cases")
                except HTTPError as exc:
                    if exc.code != 401:
                        raise RuntimeError("Guarded case endpoint returned incorrect status") from exc
                else:
                    raise RuntimeError("Unauthenticated access was allowed")
            print("Phase 6 smoke check passed: dashboard health, agent health/readiness, request IDs"
                  + (", guarded case access" if guard else ""))
            return
        except (HTTPError, URLError, OSError, ValueError, RuntimeError) as exc:
            errors.append(type(exc).__name__)
            time.sleep(delay)
    raise RuntimeError("Local smoke check failed after retry window (" + errors[-1] + ")")


def main():
    parser = argparse.ArgumentParser(description="Read-only local service smoke checks")
    parser.add_argument("--dashboard-url", default="http://127.0.0.1:18082")
    parser.add_argument("--agent-url", default="http://127.0.0.1:18091")
    parser.add_argument("--require-guard", action="store_true")
    args = parser.parse_args()
    run(args.dashboard_url, args.agent_url, args.require_guard)


if __name__ == "__main__":
    main()
