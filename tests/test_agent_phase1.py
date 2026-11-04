"""Offline tests; GitHub CI does not need FastAPI or LangGraph installed."""
import os
import tempfile
import unittest
from unittest.mock import patch

from elyraops import core
from elyraops.agent_client import AgentUnavailable, investigate
from agent_service.workflow import triage_node, retrieve_node, plan_node


class AgentPhaseOneTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.before=core.DB_PATH
        core.DB_PATH=os.path.join(self.temp.name,"agent-tests.db")
        core.initialize()

    def tearDown(self):
        core.DB_PATH=self.before
        self.temp.cleanup()

    def test_policy_retrieval_is_grounded(self):
        case=core.get_case("EC-1042")
        first=triage_node({"case":case})
        with patch.dict(os.environ, {"ELYRA_RAG_DATABASE_URL": ""}):
            hits=retrieve_node({"case":case,**first})["evidence"]
        self.assertEqual(hits[0]["id"],"POL-001")

    def test_no_key_uses_bounded_demo_planner(self):
        case=core.get_case("EC-1042")
        with patch.dict(os.environ,{"OPENAI_API_KEY":"", "GEMINI_API_KEY":""}):
            result=plan_node({"case":case,"domain":"Billing","evidence":[{"id":"POL-001"}]})
        self.assertEqual(result["mode"],"langgraph-demo")
        self.assertEqual(result["action"],core.ACTIONS["Billing"][0])
        self.assertIn("POL-001",result["reasoning"])

    def test_llm_justification_cannot_change_allowed_action(self):
        case=core.get_case("EC-1042")
        with patch.dict(os.environ,{"OPENAI_API_KEY":"testing"}), patch("agent_service.workflow.draft_rationale",return_value="Send for mandatory finance review") as model:
            result=plan_node({"case":case,"domain":"Billing","evidence":[]})
        self.assertEqual(result["action"],core.ACTIONS["Billing"][0])
        self.assertEqual(result["mode"],"langgraph-llm")
        model.assert_called_once()

    def test_no_agent_url_rejected(self):
        with patch.dict(os.environ,{"ELYRA_AGENT_URL":"http://example.com:8091"}):
            with self.assertRaises(AgentUnavailable):
                investigate("EC-1042")

    def test_existing_demo_investigation_unchanged(self):
        result=core.investigate("EC-1042")
        self.assertEqual(result["status"],"Pending approval")
        self.assertFalse(result["already_processed"])

if __name__ == "__main__":
    unittest.main()
