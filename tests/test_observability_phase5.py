"""Privacy, HTTP correlation, auth and non-retry regression tests (no external APIs)."""
from __future__ import annotations

import http.client
import io
import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import URLError

from elyraops import observability as obs, security
from elyraops.agent_client import AgentUnavailable, investigate
from elyraops.server import Handler


class ObservabilityUnitTests(unittest.TestCase):
    def test_rejects_untrusted_or_injected_request_id(self):
        for value in [None, "", "hello", "\nBearer secret", "a"*64, "x"*32]:
            rid = obs.normalize_request_id(value)
            self.assertRegex(rid, r"^[0-9a-f]{32}$")
            self.assertNotEqual(rid, value)
        rid = "f"*32
        self.assertEqual(obs.normalize_request_id(rid), rid)

    def test_context_propagates_and_resets(self):
        self.assertIsNone(obs.current_request_id())
        with obs.request_context("c"*32):
            self.assertEqual(obs.current_request_id(), "c"*32)
        self.assertIsNone(obs.current_request_id())

    def test_route_labels_never_include_case_or_query(self):
        self.assertEqual(obs.route_label("/api/cases/EC-SECRETCODE", "dashboard"), "case_detail")
        self.assertEqual(obs.route_label("/v1/investigate", "agent"), "investigate")
        self.assertEqual(obs.route_label("/something/sensitive", "agent"), "other")

    def test_prometheus_metrics_without_private_labels(self):
        obs.record_request("dashboard", "POST", "/api/cases/EC-SECRET", 403, 0.04)
        output = obs.metrics_text("dashboard")
        self.assertIn("elyra_http_requests_total", output)
        self.assertIn('status_class="4xx"', output)
        self.assertIn("_bucket", output)
        self.assertNotIn("EC-SECRET", output)
        self.assertNotIn("tenant", output)

    def test_json_log_has_no_private_data(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout), obs.request_context("c"*32):
            obs.log_event("dashboard", "http_request", route="case_detail", method="GET", status=200, seconds=.03)
        entry=json.loads(stdout.getvalue())
        self.assertEqual(entry["request_id"], "c"*32)
        self.assertEqual(entry["duration_ms"], 30)
        self.assertNotIn("case_id", entry)
        self.assertNotIn("organization", entry)

    def test_agent_timeout_validation_no_network(self):
        with patch.dict(os.environ, {"ELYRA_AGENT_URL": "http://127.0.0.1:8091",
                                     "ELYRA_AGENT_TIMEOUT_SECONDS": "0", "ELYRA_SECURITY_MODE": "disabled"}):
            with self.assertRaisesRegex(AgentUnavailable, "timeout"):
                investigate("EC-SYNTHETIC")

    def test_internal_request_id_propagates_without_retry(self):
        class MockResponse:
            def __enter__(self): return self
            def __exit__(self, *_): return None
            def read(self): return b'{"case_id":"EC-123","status":"Pending approval"}'
        mock = None
        with obs.request_context("d"*32), patch.dict(os.environ, {
            "ELYRA_AGENT_URL":"http://127.0.0.1:8091", "ELYRA_SECURITY_MODE":"disabled",
            "ELYRA_AGENT_TOKEN":"", "ELYRA_AGENT_TIMEOUT_SECONDS":"15"}), patch(
            "elyraops.agent_client.urlopen", return_value=MockResponse()) as mock:
            response = investigate("EC-123")
            self.assertEqual(response["status"], "Pending approval")
            self.assertEqual(mock.call_count, 1)
            self.assertEqual(mock.call_args.args[0].headers["X-request-id"], "d"*32)
            self.assertEqual(mock.call_args.kwargs["timeout"], 15)
        with obs.request_context("d"*32), patch.dict(os.environ, {
            "ELYRA_AGENT_URL":"http://127.0.0.1:8091", "ELYRA_SECURITY_MODE":"disabled",
            "ELYRA_AGENT_TOKEN":"", "ELYRA_AGENT_TIMEOUT_SECONDS":"15"}), patch(
            "elyraops.agent_client.urlopen", side_effect=URLError("unreachable")) as mock:
            with self.assertRaises(AgentUnavailable):
                investigate("EC-123")
            self.assertEqual(mock.call_count, 1)


class DashboardObservabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(5)

    def get(self, path, headers=None):
        conn=http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            conn.request("GET",path,headers=headers or {})
            r=conn.getresponse()
            return r.status,dict(r.getheaders()),r.read()
        finally:
            conn.close()

    def test_dashboard_returns_request_id_and_no_unsafe_log(self):
        out = io.StringIO()
        with redirect_stdout(out):
            status,headers,_ = self.get("/health?secret=SHOULD_NOT_LOG", {"X-Request-ID":"evil-not-a-correlation-id"})
            # HTTP response completion can precede the handler's finally/logging
            # block on another thread; wait briefly without relying on arbitrary sleeps.
            import time
            for _ in range(40):
                if '"route":"health"' in out.getvalue():
                    break
                time.sleep(0.005)
        self.assertEqual(status,200)
        self.assertRegex(headers["X-Request-ID"],r"^[0-9a-f]{32}$")
        self.assertNotIn("SHOULD_NOT_LOG",out.getvalue())
        self.assertIn('"route":"health"',out.getvalue())

    def test_metrics_requires_internal_token_in_guarded_mode(self):
        with patch.dict(os.environ, {"ELYRA_SECURITY_MODE":"required", "ELYRA_AGENT_TOKEN":"i"*40}):
            status,_,_ = self.get("/metrics")
            self.assertEqual(status,401)
            status,_,data = self.get("/metrics",{"X-Agent-Token":"i"*40})
            self.assertEqual(status,200)
            self.assertIn(b"elyra_http_requests_total",data)


try:
    import fastapi
    import httpx
    HAS_FASTAPI=True
except ImportError:
    HAS_FASTAPI=False


@unittest.skipUnless(HAS_FASTAPI,"Optional FastAPI + httpx")
class AgentObservabilityTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from agent_service.app import app
        self.client=TestClient(app)

    def test_health_propagates_correlation(self):
        response=self.client.get("/health",headers={"X-Request-ID":"a"*32})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers["x-request-id"],"a"*32)

    def test_agent_metrics_token_guard(self):
        with patch.dict(os.environ,{"ELYRA_SECURITY_MODE":"required", "ELYRA_AGENT_TOKEN":"i"*40}):
            self.assertEqual(self.client.get("/metrics").status_code,401)
            response=self.client.get("/metrics",headers={"X-Agent-Token":"i"*40})
            self.assertEqual(response.status_code,200)
            self.assertIn("elyra_http_request_duration_seconds", response.text)

    def test_readiness_in_unconfigured_demo_mode(self):
        from agent_service import rag_pg
        with patch.dict(os.environ,{"ELYRA_CASES_DATABASE_URL":"","ELYRA_RAG_RLS_MODE":"",
                                     "ELYRA_SECURITY_MODE":"disabled"}):
            response=self.client.get("/ready")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()["status"],"ready")

    def test_readiness_fails_closed_when_db_down(self):
        from elyraops import pg_cases
        with patch.dict(os.environ,{"ELYRA_CASES_DATABASE_URL":"postgresql://synthetic.invalid/db", "ELYRA_RAG_RLS_MODE":""}), patch.object(
            pg_cases,"verify_backend",side_effect=pg_cases.CaseStoreUnavailable("synthetic unavailable")):
            response=self.client.get("/ready")
        self.assertEqual(response.status_code,503)
        self.assertNotIn("synthetic.invalid",response.text)


if __name__=="__main__":
    unittest.main()
