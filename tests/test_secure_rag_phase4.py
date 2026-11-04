"""Phase 4 secure RAG regressions. Live tests use disposable synthetic vectors."""
from __future__ import annotations

import os
import uuid
import unittest
from unittest.mock import patch

from agent_service import rag_pg


class SecureRagOfflineTests(unittest.TestCase):
    def test_secure_flag_requires_explicit_value(self):
        with patch.dict(os.environ, {"ELYRA_RAG_RLS_MODE": "maybe"}):
            with self.assertRaises(rag_pg.RagUnavailable):
                rag_pg.secure_rag_enabled()

    def test_guarded_mode_rejects_unguarded_service(self):
        with patch.dict(os.environ, {"ELYRA_RAG_RLS_MODE": "required", "ELYRA_SECURITY_MODE": "disabled",
                                     "ELYRA_CASES_DATABASE_URL": "postgresql://example.invalid/db"}):
            with self.assertRaises(rag_pg.RagUnavailable):
                rag_pg._runtime_url("Tenant A")

    def test_guarded_mode_rejects_no_nonowner_url(self):
        with patch.dict(os.environ, {"ELYRA_RAG_RLS_MODE": "required", "ELYRA_SECURITY_MODE": "required",
                                     "ELYRA_CASES_DATABASE_URL": ""}):
            with self.assertRaises(rag_pg.RagUnavailable):
                rag_pg._runtime_url("Tenant A")

    def test_shared_is_not_an_authenticated_tenant(self):
        with patch.dict(os.environ, {"ELYRA_RAG_RLS_MODE": "required", "ELYRA_SECURITY_MODE": "required",
                                     "ELYRA_CASES_DATABASE_URL": "postgresql://example.invalid/db"}):
            with self.assertRaises(rag_pg.RagUnavailable):
                rag_pg._runtime_url("shared")

    def test_no_silent_keyword_fallback_when_protected(self):
        case = {"title": "Billing", "description": "Duplicate charge", "domain": "Billing", "organization": "Tenant A"}
        with patch.dict(os.environ, {"ELYRA_RAG_RLS_MODE": "required", "ELYRA_SECURITY_MODE": "required",
                                     "ELYRA_CASES_DATABASE_URL": "", "ELYRA_RAG_DATABASE_URL": ""}):
            with self.assertRaises(rag_pg.RagUnavailable):
                rag_pg.retrieve_for_case(case)

    def test_no_embedding_request_before_secure_scope_validation(self):
        with patch.dict(os.environ, {"ELYRA_RAG_RLS_MODE": "required", "ELYRA_SECURITY_MODE": "required",
                                     "ELYRA_CASES_DATABASE_URL": ""}), patch.object(rag_pg, "embedding") as emb:
            with self.assertRaises(rag_pg.RagUnavailable):
                rag_pg.search("duplicate payment", "Billing", "Tenant A")
            emb.assert_not_called()

    def test_explicit_legacy_demo_mode_is_still_opt_in(self):
        with patch.dict(os.environ, {"ELYRA_RAG_RLS_MODE": ""}):
            self.assertFalse(rag_pg.secure_rag_enabled())


@unittest.skipUnless(os.environ.get("ELYRA_SECURE_RAG_LIVE_TEST") == "1",
                     "Set ELYRA_SECURE_RAG_LIVE_TEST=1 for disposable PostgreSQL integration")
class SecureRagLiveTests(unittest.TestCase):
    def test_rls_restricts_raw_sql_vector_and_hybrid_search(self):
        import psycopg
        from pgvector import Vector
        from pgvector.psycopg import register_vector
        admin = os.environ["ELYRA_RLS_ADMIN_DATABASE_URL"]
        runtime = os.environ["ELYRA_CASES_DATABASE_URL"]
        a = "Test Rag A " + uuid.uuid4().hex[:10]
        b = "Test Rag B " + uuid.uuid4().hex[:10]
        doc_a = "POL-RA-" + uuid.uuid4().hex[:12]
        doc_b = "POL-RB-" + uuid.uuid4().hex[:12]
        doc_shared = "POL-RS-" + uuid.uuid4().hex[:12]
        doc_ids = [doc_a, doc_b, doc_shared]
        vector = "[" + ",".join(["1"] + ["0"] * (rag_pg.DIMENSION - 1)) + "]"
        try:
            with psycopg.connect(admin) as conn:
                for tenant, doc in ((a, doc_a), (b, doc_b), ("shared", doc_shared)):
                    conn.execute("""INSERT INTO public.rag_chunks
                        (tenant_id,document_id,chunk_index,domain,title,content,embedding_model,embedding)
                        VALUES (%s,%s,0,'Billing','Synthetic billing','duplicate payment for test',%s,%s::vector)
                    """, (tenant, doc, rag_pg.EMBEDDING_MODEL, vector))

            with patch.dict(os.environ, {"ELYRA_RAG_RLS_MODE": "required", "ELYRA_SECURITY_MODE": "required"}):
                with rag_pg.secure_rag_connection(a) as conn:
                    records = conn.execute("SELECT document_id FROM public.rag_chunks").fetchall()
                    visible = {r["document_id"] for r in records}
                    self.assertIn(doc_a, visible)
                    self.assertIn(doc_shared, visible)
                    self.assertNotIn(doc_b, visible)
                    near = conn.execute("""SELECT document_id FROM public.rag_chunks
                        WHERE domain='Billing' ORDER BY embedding <=> %s LIMIT 20""",
                        (Vector([1.0] + [0.0] * (rag_pg.DIMENSION - 1)),)).fetchall()
                    self.assertNotIn(doc_b, {r["document_id"] for r in near})

                with rag_pg.secure_rag_connection(b) as conn:
                    seen = {r["document_id"] for r in conn.execute("SELECT document_id FROM public.rag_chunks").fetchall()}
                    self.assertIn(doc_b, seen)
                    self.assertIn(doc_shared, seen)
                    self.assertNotIn(doc_a, seen)

                # Exact production search path with synthetic Gemini output (no API calls).
                with patch.object(rag_pg, "embedding", return_value=[1.0] + [0.0] * (rag_pg.DIMENSION - 1)):
                    results = rag_pg.search("duplicate payment", "Billing", a, limit=10)
                    ids = {r["id"] for r in results}
                    self.assertIn(doc_a, ids)
                    self.assertIn(doc_shared, ids)
                    self.assertNotIn(doc_b, ids)

                with psycopg.connect(runtime) as conn:
                    # No SET LOCAL tenant means not even shared docs are visible.
                    self.assertEqual(conn.execute("SELECT document_id FROM public.rag_chunks").fetchall(), [])
                    with self.assertRaises(psycopg.Error):
                        conn.execute("""INSERT INTO public.rag_chunks
                            (tenant_id,document_id,chunk_index,domain,title,content,embedding_model,embedding)
                            VALUES ('shared','SHOULD-NOT-WRITE',0,'Billing','x','x',%s,%s::vector)""",
                            (rag_pg.EMBEDDING_MODEL, vector))
        finally:
            # Admin connection removes only generated synthetic rows.
            with psycopg.connect(admin) as conn:
                conn.execute("DELETE FROM public.rag_chunks WHERE document_id = ANY(%s)", (doc_ids,))


if __name__ == "__main__":
    unittest.main()
