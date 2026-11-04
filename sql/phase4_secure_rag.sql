-- Phase 4: database-enforced RAG read isolation.
-- Apply only as trusted local DB owner, after Phase 3B setup and RAG init.
-- Existing shared and tenant-scoped embeddings are preserved without reindexing.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elyra_cases_runtime') THEN
    RAISE EXCEPTION 'Run Phase 3B setup_rls.py before Phase 4 RAG setup';
  END IF;
  IF to_regclass('public.rag_chunks') IS NULL THEN
    RAISE EXCEPTION 'Run python -m agent_service.rag_pg init first';
  END IF;
END $$;

REVOKE ALL ON TABLE public.rag_chunks FROM PUBLIC;
GRANT SELECT ON TABLE public.rag_chunks TO elyra_cases_runtime;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON TABLE public.rag_chunks FROM elyra_cases_runtime;

ALTER TABLE public.rag_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rag_chunks FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rag_tenant_read ON public.rag_chunks;
CREATE POLICY rag_tenant_read ON public.rag_chunks
  FOR SELECT TO elyra_cases_runtime
  USING (
    NULLIF(current_setting('elyra.tenant_id', true), '') IS NOT NULL
    AND (tenant_id = 'shared'
         OR tenant_id = NULLIF(current_setting('elyra.tenant_id', true), ''))
  );

-- FORCE RLS also affects the table owner. The owner is a trusted local
-- ingestion/migration administrator, never the FastAPI runtime connection.
-- This policy preserves existing CLI seeding and manual ingestion.
DROP POLICY IF EXISTS rag_owner_admin ON public.rag_chunks;
DO $$
BEGIN
  EXECUTE format(
    'CREATE POLICY rag_owner_admin ON public.rag_chunks FOR ALL TO %I USING (true) WITH CHECK (true)',
    current_user
  );
END $$;
