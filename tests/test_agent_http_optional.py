"""Optional API and graph smoke tests; skip when add-on dependencies are absent."""
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch
from elyraops import core

HAS_HTTP = all(importlib.util.find_spec(x) for x in ("fastapi","httpx"))
HAS_LANGGRAPH = importlib.util.find_spec("langgraph") is not None


@unittest.skipUnless(HAS_HTTP, "FastAPI + httpx are optional")
class AgentHTTPTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from agent_service.app import app
        self.temp=tempfile.TemporaryDirectory()
        self.previous=core.DB_PATH
        core.DB_PATH=os.path.join(self.temp.name, "api-tests.db")
        core.initialize()
        self.client=TestClient(app)

    def tearDown(self):
        core.DB_PATH=self.previous
        self.temp.cleanup()

    def test_api_commits_workflow_and_is_idempotent(self):
        def graph(case):
            return {"domain":case["domain"], "priority":case["priority"],
                    "evidence":[{"id":"POL-001","title":"Billing","excerpt":"review required","score":2}],
                    "action":core.ACTIONS["Billing"][0],"reasoning":"Manual finance approval is required.","mode":"test-graph"}
        with patch("agent_service.app.run_graph",side_effect=graph):
            r=self.client.post("/v1/investigate",json={"case_id":"EC-1042"})
            self.assertEqual(r.status_code,200,r.text)
            self.assertFalse(r.json()["already_processed"])
            repeated=self.client.post("/v1/investigate",json={"case_id":"EC-1042"})
        self.assertTrue(repeated.json()["already_processed"])
        c=core.get_case("EC-1042")
        self.assertEqual(c["status"],"Pending approval")
        self.assertEqual(sum(x["type"]=="approval_requested" for x in c["events"]),1)
        self.assertEqual(c["evidence"][0]["id"],"POL-001")

    def test_bad_case_validation(self):
        r=self.client.post("/v1/investigate",json={"case_id":"../bad"})
        self.assertEqual(r.status_code,422)


@unittest.skipUnless(HAS_LANGGRAPH, "LangGraph optional dependency not installed")
class ActualLangGraphSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.previous=core.DB_PATH
        core.DB_PATH=os.path.join(self.temp.name, "graph-tests.db")
        core.initialize()

    def tearDown(self):
        core.DB_PATH=self.previous
        self.temp.cleanup()

    def test_full_graph_in_demo_mode(self):
        from agent_service.workflow import run_graph
        with patch.dict(os.environ,{"OPENAI_API_KEY":"", "GEMINI_API_KEY":"", "ELYRA_RAG_DATABASE_URL":""}):
            result=run_graph(core.get_case("EC-1042"))
        self.assertEqual(result["mode"],"langgraph-demo")
        self.assertEqual(result["evidence"][0]["id"],"POL-001")
