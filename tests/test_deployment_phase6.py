"""Offline container opt-in, safety checks and smoke-client unit tests."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from elyraops.agent_client import AgentUnavailable, investigate
from elyraops.server import validate_local_listener
from scripts.phase6_smoke import validate_url, run

ROOT = Path(__file__).resolve().parents[1]


class ListenerSafetyTests(unittest.TestCase):
    def test_guarded_public_bind_rejected_outside_explicit_compose(self):
        with patch.dict(os.environ, {"ELYRA_SECURITY_MODE":"required", "ELYRA_LOCAL_COMPOSE":""}):
            with self.assertRaisesRegex(RuntimeError, "localhost"):
                validate_local_listener("0.0.0.0")

    def test_compose_requires_rag_and_postgres_guard(self):
        env={"ELYRA_SECURITY_MODE":"required", "ELYRA_LOCAL_COMPOSE":"1",
             "ELYRA_CASES_DATABASE_URL":"postgresql://placeholder.invalid/db", "ELYRA_RAG_RLS_MODE":"required"}
        with patch.dict(os.environ, env):
            validate_local_listener("0.0.0.0")
        env["ELYRA_RAG_RLS_MODE"] = ""
        with patch.dict(os.environ, env):
            with self.assertRaises(RuntimeError): validate_local_listener("0.0.0.0")
        env["ELYRA_RAG_RLS_MODE"]="required"
        env["ELYRA_SECURITY_MODE"]="disabled"
        with patch.dict(os.environ, env):
            with self.assertRaises(RuntimeError): validate_local_listener("0.0.0.0")

    def test_normal_localhost_guarded_allowed(self):
        with patch.dict(os.environ, {"ELYRA_SECURITY_MODE":"required", "ELYRA_LOCAL_COMPOSE":""}):
            validate_local_listener("127.0.0.1")


class ComposeAgentClientTests(unittest.TestCase):
    def test_compose_agent_requires_explicit_opt_in(self):
        with patch.dict(os.environ, {"ELYRA_LOCAL_COMPOSE":"", "ELYRA_AGENT_URL":"http://elyra-agent:8091",
                                     "ELYRA_SECURITY_MODE":"disabled"}):
            with self.assertRaisesRegex(AgentUnavailable,"trusted"):
                investigate("EC-TEST")

    def test_compose_agent_only_allows_exact_service_port(self):
        with patch.dict(os.environ, {"ELYRA_LOCAL_COMPOSE":"1", "ELYRA_SECURITY_MODE":"disabled"}):
            for url in ("http://elyra-agent:8092", "http://host.docker.internal:8091",
                        "http://elyra-agent:8091/admin", "http://elyra-agent:8091/?x=1"):
                with patch.dict(os.environ, {"ELYRA_AGENT_URL": url}):
                    with self.assertRaisesRegex(AgentUnavailable,"trusted"):
                        investigate("EC-TEST")

    def test_compose_request_has_expected_internal_endpoint(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return b'{"case_id":"EC-TEST","status":"Pending approval"}'
        env={"ELYRA_LOCAL_COMPOSE":"1","ELYRA_AGENT_URL":"http://elyra-agent:8091",
             "ELYRA_SECURITY_MODE":"disabled", "ELYRA_AGENT_TOKEN":""}
        with patch.dict(os.environ,env), patch('elyraops.agent_client.urlopen',return_value=Response()) as fetch:
            self.assertEqual(investigate("EC-TEST")["status"],"Pending approval")
            self.assertEqual(fetch.call_args.args[0].full_url,"http://elyra-agent:8091/v1/investigate")


class DeploymentContractTests(unittest.TestCase):
    def test_compose_has_only_loopback_dashboard_publish(self):
        content=(ROOT/'compose.phase6.yml').read_text()
        self.assertIn('"127.0.0.1:18082:8082"',content)
        self.assertNotIn('8091:8091',content)
        self.assertIn('external: true',content)
        self.assertIn('read_only: true',content)
        self.assertIn('required',content)
        self.assertIn('service_healthy',content)

    def test_build_context_excludes_secrets(self):
        ignore=(ROOT/'.dockerignore').read_text()
        self.assertIn('.env.*',ignore)
        self.assertIn('.venv/',ignore)

    def test_legacy_compose_defaults_to_host_loopback(self):
        self.assertIn('127.0.0.1:8080:8080',(ROOT/'docker-compose.yml').read_text())

    def test_smoke_url_refuses_external_network(self):
        for url in ('https://example.com:1234','http://example.com:1234','http://127.0.0.1:80/x',
                    'http://127.0.0.1:80/?token=abc'):
            with self.assertRaises(ValueError): validate_url(url)
        validate_url('http://elyra-agent:8091')

    def test_smoke_success_with_local_mocks(self):
        from unittest.mock import Mock
        headers={"X-Request-ID":"a"*32}
        def fake(url):
            if url.endswith('/api/cases'):
                from urllib.error import HTTPError
                raise HTTPError(url,401,'Unauthorized',{},None)
            fields=({"status":"ready"} if url.endswith('/ready') else
                    {"enabled":True} if url.endswith('/api/auth/config') else {"status":"ok"})
            return fields
        with patch('scripts.phase6_smoke.get_json',side_effect=fake):
            run('http://elyra-dashboard:8082','http://elyra-agent:8091',guard=True,attempts=1,delay=0)


    def test_smoke_retries_connection_reset(self):
        responses = [
            ConnectionResetError("Container starting"),
            {"status": "ok"},
            {"status": "ok"},
            {"status": "ready"},
        ]
        with patch("scripts.phase6_smoke.get_json", side_effect=responses):
            with patch("scripts.phase6_smoke.time.sleep") as sleep:
                run(
                    "http://127.0.0.1:18082",
                    "http://127.0.0.1:18091",
                    attempts=2,
                    delay=0,
                )
                sleep.assert_called_once()


if __name__ == '__main__': unittest.main()
