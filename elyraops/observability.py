"""Bounded, privacy-preserving local HTTP observability. No external dependencies.

Never records request bodies, credentials, tenant names, case IDs, or query strings.
Metrics are process-local (not aggregated across workers or process restarts).
"""
from __future__ import annotations

import contextvars
import json
import math
import re
import sys
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone

_REQUEST_ID = contextvars.ContextVar("elyra_request_id", default=None)
_REQUEST_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60)
_LOCK = threading.Lock()
_REQUESTS: dict[tuple[str, str, str, str], int] = defaultdict(int)
_DURATIONS: dict[tuple[str, str, str, str], list[float]] = {}


def normalize_request_id(value: str | None) -> str:
    """Keep an innocuous, bounded correlation ID or make a fresh one."""
    return value if isinstance(value, str) and _REQUEST_ID_PATTERN.fullmatch(value) else uuid.uuid4().hex


def current_request_id() -> str | None:
    return _REQUEST_ID.get()


@contextmanager
def request_context(request_id: str):
    token = _REQUEST_ID.set(request_id)
    try:
        yield
    finally:
        _REQUEST_ID.reset(token)


def route_label(path: str, service: str) -> str:
    """Fixed labels avoid cardinality and accidental leaking of case IDs."""
    if path == "/health":
        return "health"
    if path == "/ready":
        return "ready"
    if path == "/metrics":
        return "metrics"
    if service == "agent":
        return "investigate" if path == "/v1/investigate" else "other"
    if path in {"/", "/index.html", "/app.js", "/styles.css"}:
        return "web_asset"
    if path == "/api/dashboard":
        return "dashboard"
    if path in {"/api/cases", "/api/knowledge"}:
        return "case_list"
    if path.startswith("/api/auth/"):
        return "auth"
    if re.fullmatch(r"/api/cases/EC-[A-Za-z0-9-]+(?:/(?:investigate|decision))?", path):
        return "case_detail"
    return "other"


def record_request(service: str, method: str, path: str, status: int, seconds: float) -> None:
    if service not in {"agent", "dashboard"}:
        raise ValueError("Unsupported service label")
    label = route_label(path, service)
    method = method if method in {"GET", "POST", "HEAD"} else "OTHER"
    code = str(status // 100) + "xx" if 100 <= status < 600 else "other"
    seconds = max(0.0, min(3600.0, seconds if math.isfinite(seconds) else 3600.0))
    key = (service, method, label, code)
    with _LOCK:
        _REQUESTS[key] += 1
        if key not in _DURATIONS:
            _DURATIONS[key] = [0.0, 0.0] + [0.0] * len(_BUCKETS)
        data = _DURATIONS[key]
        data[0] += 1
        data[1] += seconds
        for i, bound in enumerate(_BUCKETS, start=2):
            if seconds <= bound:
                data[i] += 1


def metrics_text(service: str) -> str:
    """Prometheus 0.0.4 exposition for one in-process service only."""
    if service not in {"agent", "dashboard"}:
        raise ValueError("Unsupported service label")
    with _LOCK:
        counts = sorted((k, v) for k, v in _REQUESTS.items() if k[0] == service)
        durations = sorted((k, list(v)) for k, v in _DURATIONS.items() if k[0] == service)
    lines = [
        "# HELP elyra_http_requests_total HTTP requests grouped by bounded route and status class.",
        "# TYPE elyra_http_requests_total counter",
    ]
    for (svc, method, route, code), value in counts:
        labels = f'service="{svc}",method="{method}",route="{route}",status_class="{code}"'
        lines.append(f"elyra_http_requests_total{{{labels}}} {value}")
    lines += [
        "# HELP elyra_http_request_duration_seconds HTTP request latency in seconds.",
        "# TYPE elyra_http_request_duration_seconds histogram",
    ]
    for (svc, method, route, code), data in durations:
        labels = f'service="{svc}",method="{method}",route="{route}",status_class="{code}"'
        for i, bound in enumerate(_BUCKETS, start=2):
            lines.append(f'elyra_http_request_duration_seconds_bucket{{{labels},le="{bound}"}} {int(data[i])}')
        lines.append(f'elyra_http_request_duration_seconds_bucket{{{labels},le="+Inf"}} {int(data[0])}')
        lines.append(f"elyra_http_request_duration_seconds_sum{{{labels}}} {data[1]:.6f}")
        lines.append(f"elyra_http_request_duration_seconds_count{{{labels}}} {int(data[0])}")
    return "\n".join(lines) + "\n"


def log_event(service: str, event: str, *, route: str | None = None,
              method: str | None = None, status: int | None = None,
              seconds: float | None = None, request_id: str | None = None) -> None:
    """Allowlisted fields only: deliberately omit payloads, exceptions, identities."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "service": service,
        "event": event,
        "request_id": request_id if request_id is not None else current_request_id(),
    }
    if route is not None:
        entry["route"] = route
    if method is not None:
        entry["method"] = method
    if status is not None:
        entry["status"] = int(status)
    if seconds is not None:
        entry["duration_ms"] = round(max(0.0, seconds) * 1000, 2)
    print(json.dumps(entry, separators=(",", ":"), ensure_ascii=True), file=sys.stdout, flush=True)


def finish_http_request(service: str, method: str, path: str, status: int, started: float, rid: str) -> None:
    seconds = time.perf_counter() - started
    record_request(service, method, path, status, seconds)
    log_event(service, "http_request", route=route_label(path, service), method=method,
              status=status, seconds=seconds, request_id=rid)
