"""Opt-in real pgvector integration: ELYRA_RAG_TEST_DATABASE_URL + GEMINI_API_KEY required.

Requires `python -m agent_service.rag_pg seed` first; may consume Gemini API quota.
"""
import os
import unittest
from unittest.mock import patch
from agent_service import rag_pg


@unittest.skipUnless(os.environ.get("ELYRA_RAG_TEST_DATABASE_URL") and os.environ.get("GEMINI_API_KEY"),
                     "Set test database URL and Gemini key for live PostgreSQL integration")
class PostgresRagIntegrationTests(unittest.TestCase):
    def test_domain_filtered_real_vector_search(self):
        with patch.dict(os.environ, {"ELYRA_RAG_DATABASE_URL": os.environ.get("ELYRA_RAG_TEST_DATABASE_URL", "")}):
            hits = rag_pg.search("duplicate subscription charge refund", "Billing", "Synthetic Organization")
        self.assertIn("POL-001", [h["id"] for h in hits])
        self.assertTrue(all(h["domain"] == "Billing" for h in hits))


if __name__ == "__main__":
    unittest.main()
