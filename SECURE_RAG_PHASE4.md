# ElyraOps AI — Phase 4: Secure RAG Row-Level Security

This is an **opt-in local demonstration** of PostgreSQL-enforced tenant isolation for RAG documents. It complements Phase 3B case/event RLS. It does not provide OIDC, managed identities, production authorization, or a tenant-safe administrative API. **Use only synthetic data; do not expose these services to the internet.**

## Threat model and boundaries

- RAG documents reside in the existing `public.rag_chunks` table. Existing vector embeddings are preserved. Public `shared` policy rows are visible to all **authenticated tenants**, while private tenant rows are visible only within the transaction's tenant scope.
- In protected mode, the FastAPI search path uses the **existing** `elyra_cases_runtime` PostgreSQL role from `.env.rls`. It may SELECT from RAG but cannot INSERT, UPDATE, or DELETE RAG chunks. Row-level policies are enforced by PostgreSQL and tested using SQL without application tenant filters.
- Every retrieval transaction binds the tenant with `set_config('elyra.tenant_id', tenant, true)` (transaction-local), then performs vector and full-text search. Missing tenant context reveals **no documents, including shared policies**.
- The existing RAG ingestion CLI remains a trusted **local administrator** workflow that uses `ELYRA_RAG_DATABASE_URL` and the owner connection, not the HTTP runtime. No authenticated document ingestion API is added. Do not run CLI ingestion with untrusted documents.
- The trusted organization is carried by the Phase 3A authenticated dashboard's internal request, then checked against the case by the agent service. It remains a string rather than a canonical tenant ID. If arbitrary SQL executes as the runtime role, the session setting may be changed; this defense-in-depth design is **not** a substitute for preventing SQL injection or using a trusted identity broker.
- The knowledge hub's original SQLite policy catalog is **not** migrated or RLS-protected. Only the `public.rag_chunks` PostgreSQL table receives document RLS in this phase.

## 1. Apply upgrade on clean feature branch

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
unzip -o ~/Downloads/ElyraOps-Phase4-Secure-RAG-RLS-upgrade.zip
python scripts/apply_secure_rag_phase4.py
```

The patch script checks the current source files before replacing them and stops rather than overwriting unexpected local modifications.

## 2. Offline tests

```bash
env -u ELYRA_RAG_RLS_MODE -u ELYRA_SECURITY_MODE -u ELYRA_ACCESS_TOKENS_JSON \
    -u ELYRA_AGENT_TOKEN -u ELYRA_CASES_DATABASE_URL -u ELYRA_RAG_DATABASE_URL \
    -u ELYRA_RAG_TEST_DATABASE_URL -u ELYRA_SECURE_RAG_LIVE_TEST \
    -u ELYRA_RLS_LIVE_TEST -u GEMINI_API_KEY -u OPENAI_API_KEY \
    python -m unittest discover -s tests -v
```

## 3. Apply RAG RLS to existing PostgreSQL DB

Stop the FastAPI server using `Control+C` before changing access policies. The dashboard can remain stopped as well. Verify that the Phase 3B `.env.rls` is present and Docker database is healthy:

```bash
docker compose -f docker-compose.rag.yml ps
export ELYRA_RLS_ADMIN_DATABASE_URL='postgresql://elyra_demo:elyra_demo_pw_change_for_real_use@127.0.0.1:5447/elyra_rag'
python scripts/setup_secure_rag.py  # preview, no changes
python scripts/setup_secure_rag.py --apply
```

This keeps all previously indexed `POL-001` through `POL-006` records. It grants SELECT to `elyra_cases_runtime`, while preventing runtime RAG modifications. It applies both ENABLE and FORCE RLS and adds a separate local owner policy to preserve trusted seeding/ingestion.

## 4. Live tenant-isolation test

In the same Terminal:

```bash
set -a
source .env.security
source .env.rls
set +a
ELYRA_SECURE_RAG_LIVE_TEST=1 python -m unittest discover -s tests -p 'test_secure_rag_phase4.py' -v
```

The test adds **synthetic** 768-dimensional vectors, tests raw unfiltered SELECTs, pgvector ordering and hybrid search for two independent tenants, confirms `shared` documents remain visible to authenticated tenants, and verifies the runtime role cannot write. It deletes only its own generated test records. **It makes no Gemini API requests.**

## 5. Restart FastAPI using RLS-protected retrieval

Stop the old FastAPI process first (`Control+C`), then in the FastAPI Terminal:

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
set -a; source .env.security; source .env.rls; set +a
export ELYRA_RAG_RLS_MODE=required
unset ELYRA_RAG_DATABASE_URL  # privileged owner URL must NOT be in the FastAPI runtime
read -s 'GEMINI_API_KEY?Paste Gemini API key: '; echo; export GEMINI_API_KEY
python -m uvicorn agent_service.app:app --host 127.0.0.1 --port 8091
```

The dashboard remains secured as in Phase 3B, loading `.env.security` and `.env.rls`, setting `ELYRA_AGENT_URL=http://127.0.0.1:8091` and `PORT=8082`.

Create a **new** Billing case under Synthetic Organization, investigate it, and expect evidence `POL-001`, a Gemini rationale, and an explicit approval gate. Existing cases are not automatically reprocessed.

## 6. GitHub Actions integration

`.github/workflows/ci.yml` now adds `secure-rag-postgres`: a disposable pgvector database, Phase 3B runtime role, RAG RLS migration, and direct SQL isolation tests with synthetic vectors. This job does not need Gemini or a private secret. The separate Python 3.12/3.13 offline unit-test matrix remains.

## Limitations

This is not a production-grade security system. RAG document ingestion remains owner-only local CLI, the knowledge-hub SQLite table remains unscoped, database credentials are local, there is no OIDC/MFA/canonical tenant identity, and API access to real records must remain disabled. Database-owner privileges are entrusted to administration; never pass that URL to the application runtime. Do not cite this work as production zero-trust or a fully isolated multi-tenant SaaS architecture.
