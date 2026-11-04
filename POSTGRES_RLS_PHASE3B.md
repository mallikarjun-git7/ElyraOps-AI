# ElyraOps AI — Phase 3B: PostgreSQL case store + RLS (local demonstration)

**Current scope**: Optional PostgreSQL storage for cases and their audit events. Cases and events use a non-owner runtime database role, tenant-scoped transactions, `ENABLE` + `FORCE ROW LEVEL SECURITY`, and `USING`/`WITH CHECK` policies. The **default SQLite path remains unchanged** until you explicitly set `ELYRA_CASES_DATABASE_URL`.

This is not production authentication. The tenant is the authenticated Phase 3A principal's organization **string**, not a canonical tenant UUID. The app controls the per-transaction tenant setting. A person with the application database password can set a different tenant manually; this isolation layer is defense-in-depth against omitted application query predicates, **not an authorization boundary against compromised database credentials or arbitrary SQL injection**. `rag_chunks` is a separate demo document store without RLS; it still uses explicit domain/organization filtering. Neither the vector store nor the local SQLite knowledge catalog is migrated here.

## 1. Prepare the database (Terminal C, with Docker running)

Ensure the existing `docker-compose.rag.yml` PostgreSQL container is healthy:

```bash
docker compose -f docker-compose.rag.yml ps
source .venv/bin/activate
export ELYRA_RLS_ADMIN_DATABASE_URL='postgresql://elyra_demo:elyra_demo_pw_change_for_real_use@127.0.0.1:5447/elyra_rag'
python scripts/setup_rls.py
```

The setup creates a distinct login `elyra_cases_runtime` with a newly randomized password, two tables in schema `elyra_rls`, required RLS policies and owner-only `.env.rls` (0600). The existing RAG database/tables remain untouched. The script will refuse to overwrite an existing `.env.rls` or rotate an existing role unexpectedly. **Do not share or commit `.env.rls`**, and use only the local synthetic data.

## 2. Dry-run and migrate one tenant (optional)

If you want to retain the cases already created in SQLite, in a new Terminal:

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
set -a; source .env.security; source .env.rls; set +a
python scripts/migrate_sqlite_cases.py --organization 'Synthetic Organization'
```

Confirm the counts. Then, only if you want to copy those cases:

```bash
python scripts/migrate_sqlite_cases.py --organization 'Synthetic Organization' --apply
```

Existing PostgreSQL rows are never overwritten. The original SQLite file is unchanged. Other organizations' records are not copied. Do **not** run this against real customer records.

## 3. Start both services with PostgreSQL cases and Gemini RAG

Stop your existing dashboard and FastAPI terminals using Control+C first.

**Terminal A — FastAPI / LangGraph / Gemini**

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
set -a; source .env.security; source .env.rls; set +a
export ELYRA_RAG_DATABASE_URL='postgresql://elyra_demo:elyra_demo_pw_change_for_real_use@127.0.0.1:5447/elyra_rag'
read -s 'GEMINI_API_KEY?Paste Gemini key: '; echo; export GEMINI_API_KEY
python -m uvicorn agent_service.app:app --host 127.0.0.1 --port 8091
```

**Terminal B — secured dashboard**

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
set -a; source .env.security; source .env.rls; set +a
export ELYRA_AGENT_URL=http://127.0.0.1:8091
export PORT=8082
python -m elyraops.server
```

The dashboard should show only that role's tenant cases. A case created by an Analyst must be invisible from another tenant even for SQL queries lacking `WHERE tenant_id = ...`. An Approver should see the same tenant's pending cases. No actual refunds are executed.

## 4. Test

**Offline CI suite** (always run before pushing, no network or secrets):

```bash
env -u ELYRA_SECURITY_MODE -u ELYRA_ACCESS_TOKENS_JSON -u ELYRA_AGENT_TOKEN -u ELYRA_CASES_DATABASE_URL -u ELYRA_RAG_DATABASE_URL -u ELYRA_RAG_TEST_DATABASE_URL -u GEMINI_API_KEY -u OPENAI_API_KEY python -m unittest discover -s tests -v
```

**Opt-in live RLS test**, with `.env.security` and `.env.rls` loaded, and `ELYRA_RLS_ADMIN_DATABASE_URL` available for cleanup:

```bash
ELYRA_RLS_LIVE_TEST=1 python -m unittest tests.test_postgres_rls_phase3b -v
```

Expected test properties: own-tenant case visible; other-tenant case hidden even with an unscoped `SELECT`; other-tenant case events hidden; changing the case tenant fails under `WITH CHECK`. Do not count this as passed until it runs against your local PostgreSQL container.

## What remains unimplemented

- RLS on the RAG document tables, plus real authorization for document ingestion.
- OIDC/PKCE/MFA, user membership and canonical tenant IDs, managed secrets, TLS and rate limiting.
- Performance/load benchmarks, advanced role-based SQL privilege separation, deployment and backup/restore.
- Database-level transaction outbox, Kafka, structured tracing and production observability.

Keep both services bound to localhost. `ELYRA_CASES_DATABASE_URL` misconfiguration **must fail closed** rather than showing unprotected SQLite cases.
