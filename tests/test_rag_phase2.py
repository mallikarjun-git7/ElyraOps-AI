"""Offline tests for retrieval isolation, scoring and Gemini embedding contract."""
import json
import math
import os
import tempfile
import unittest
from unittest.mock import patch

from elyraops import core
from agent_service import rag_pg


class RagPhaseTwoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = core.DB_PATH
        core.DB_PATH = os.path.join(self.tmp.name, "tests.db")
        core.initialize()

    def tearDown(self):
        core.DB_PATH = self.old_path
        self.tmp.cleanup()

    def test_billing_retrieval_excludes_support_procurement(self):
        with core.connect() as db:
            hits = core.retrieve(db, "duplicate payment subscription refund invoice delivery", "Billing")
        self.assertEqual([item["id"] for item in hits], ["POL-001"])
        self.assertTrue(all(item["domain"] == "Billing" for item in hits))

    def test_no_cross_domain_result_even_for_exact_words(self):
        with core.connect() as db:
            hits = core.retrieve(db, "damaged delivery return policy", "Billing")
        self.assertTrue(all(item["domain"] == "Billing" for item in hits))
        self.assertNotIn("POL-005", [item["id"] for item in hits])

    def test_default_fallback_does_not_need_postgres(self):
        case = core.get_case("EC-1042")
        with patch.dict(os.environ, {"ELYRA_RAG_DATABASE_URL": ""}):
            hits = rag_pg.retrieve_for_case(case)
        self.assertEqual([item["id"] for item in hits], ["POL-001"])

    def test_rank_fusion_merges_duplicate_chunk(self):
        a = dict(tenant_id="shared", document_id="POL-001", chunk_index=0,
                 title="Billing", domain="Billing", content="Duplicate payments")
        b = dict(tenant_id="shared", document_id="POL-009", chunk_index=0,
                 title="Billing 2", domain="Billing", content="Other")
        fused = rag_pg.fuse_ranked([a, b], [a], 2)
        self.assertEqual(fused[0]["id"], "POL-001")
        self.assertGreater(fused[0]["score"], fused[1]["score"])

    def test_chunking_has_overlap_and_progress(self):
        chunks = rag_pg.split_chunks("word " * 400, size=300, overlap=50)
        self.assertGreater(len(chunks), 2)
        self.assertLess(len(chunks), 15)
        self.assertTrue(all(chunks))

    def test_gemini_embedding_api_contract_and_normalization(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, *args): return b''
        # fake json.load to avoid needing a real key or internet.
        def fake_json_load(_): return {"embedding": {"values": [2.0] + [0.0]*767}}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-only"}), \
             patch.object(rag_pg, "urlopen", return_value=Response()) as client, \
             patch.object(rag_pg.json, "load", side_effect=fake_json_load):
            vec = rag_pg.embedding("A duplicate payment question", "RETRIEVAL_QUERY")
            req = client.call_args[0][0]
            self.assertIn("gemini-embedding-001:embedContent", req.full_url)
            payload = json.loads(req.data)
            self.assertEqual(payload["taskType"], "RETRIEVAL_QUERY")
            self.assertEqual(payload["outputDimensionality"], 768)
        self.assertEqual(len(vec), 768)
        self.assertAlmostEqual(math.sqrt(sum(x*x for x in vec)), 1.0)

    def test_embedding_requires_key(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertRaises(rag_pg.RagUnavailable):
                rag_pg.embedding("test", "RETRIEVAL_QUERY")


if __name__ == "__main__":
    unittest.main()
