-- Run as the local database owner AFTER scripts/setup_rls.py has created
-- elyra_cases_runtime. Runtime traffic must never use the owner connection.
CREATE SCHEMA IF NOT EXISTS elyra_rls;
REVOKE ALL ON SCHEMA elyra_rls FROM PUBLIC;
CREATE TABLE IF NOT EXISTS elyra_rls.case_records (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL CHECK (length(tenant_id) BETWEEN 1 AND 100),
  title TEXT NOT NULL,
  domain TEXT NOT NULL,
  priority TEXT NOT NULL,
  organization TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'Open',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  proposed_action TEXT,
  reasoning TEXT,
  evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
  workflow_run_id TEXT,
  UNIQUE (id,tenant_id),
  CONSTRAINT organization_is_tenant CHECK (organization=tenant_id)
);
CREATE TABLE IF NOT EXISTS elyra_rls.case_events (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  type TEXT NOT NULL,
  message TEXT NOT NULL,
  actor TEXT NOT NULL,
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TEXT NOT NULL,
  inserted_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY (case_id,tenant_id) REFERENCES elyra_rls.case_records(id,tenant_id)
);
CREATE INDEX IF NOT EXISTS idx_elyra_rls_cases_tenant ON elyra_rls.case_records(tenant_id, id);
CREATE INDEX IF NOT EXISTS idx_elyra_rls_events_scope ON elyra_rls.case_events(tenant_id, case_id, created_at);
ALTER TABLE elyra_rls.case_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE elyra_rls.case_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE elyra_rls.case_records FORCE ROW LEVEL SECURITY;
ALTER TABLE elyra_rls.case_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_access ON elyra_rls.case_records;
DROP POLICY IF EXISTS tenant_access ON elyra_rls.case_events;
CREATE POLICY tenant_access ON elyra_rls.case_records
  FOR ALL TO elyra_cases_runtime
  USING (tenant_id = NULLIF(current_setting('elyra.tenant_id',true),''))
  WITH CHECK (tenant_id = NULLIF(current_setting('elyra.tenant_id',true),''));
CREATE POLICY tenant_access ON elyra_rls.case_events
  FOR ALL TO elyra_cases_runtime
  USING (tenant_id = NULLIF(current_setting('elyra.tenant_id',true),''))
  WITH CHECK (tenant_id = NULLIF(current_setting('elyra.tenant_id',true),''));
REVOKE ALL ON elyra_rls.case_records,elyra_rls.case_events FROM PUBLIC;
GRANT USAGE ON SCHEMA elyra_rls TO elyra_cases_runtime;
GRANT SELECT,INSERT,UPDATE ON elyra_rls.case_records,elyra_rls.case_events TO elyra_cases_runtime;
REVOKE DELETE,TRUNCATE,REFERENCES,TRIGGER ON elyra_rls.case_records,elyra_rls.case_events FROM elyra_cases_runtime;
