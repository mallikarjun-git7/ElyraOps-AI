# ElyraOps AI — Phase 6: local Docker deployment and CI/CD checks

**Scope:** reproducible **localhost-only** Docker Compose deployment using the **existing** Phase 4 pgvector/PostgreSQL container, database tables, tenant RLS runtime role, seeded policy embeddings and data volume. No public internet/cloud deployment, OIDC, production secret vault, SLA or real execution system is claimed. Do not use real customer information.

The existing Mac-based Python services can continue on 8082/8091. Phase 6 runs separately at **http://127.0.0.1:18082**. The agent service port is not published by Phase 6; the dashboard uses `http://elyra-agent:8091` over the Compose network. The PostgreSQL storage is reused **without** running migrations or replacing volumes.

## Files and security design

- `Dockerfile.phase6` — Python 3.13 image with FastAPI, LangGraph, psycopg, pgvector, non-root runtime and no copied credentials.
- `compose.phase6.yml` — two services with health checks, read-only root filesystems, temporary SQLite knowledge caches, dropped capabilities and localhost-only dashboard port. The agent has no host port binding. The existing `elyraops-rag_default` network must exist.
- `scripts/phase6_local.sh` — local convenience wrapper; sources your existing ignored `.env.security` and `.env.rls`, checks tenant RLS with the **non-owner** connection, rewrites only the DATABASE HOST/PORT to `rag-db:5432` for Docker networking, requests Gemini key privately if missing, then builds/starts Compose. It does not change the stored configuration files.
- `scripts/phase6_smoke.py` — checks dashboard/agent liveness, agent readiness, request IDs and optionally guarded API behavior. Never writes a case or triggers an LLM call.
- `.dockerignore` excludes `.env`/`.env.*`, `.venv`, local data and generated archives from the Docker build context. `docker-compose.yml` legacy port mapping is also restricted to host loopback.
- `.github/workflows/ci.yml` builds the Phase 6 image and starts both service processes for **non-secret demo-mode** HTTP smoke checks; the existing `secure-rag-postgres` CI job independently verifies database-level RLS.
- `tests/test_observability_phase5.py` waits for asynchronous request logging before asserting, avoiding a rare race between the HTTP response and log emission.
- `load/k6_phase6.js` is a five-user, 15-second **read-only** load smoke with illustrative thresholds. Run it yourself; results are environment-dependent and not a published scalability guarantee.

Security limitations: `ELYRA_LOCAL_COMPOSE=1` deliberately permits an *in-container* listener on `0.0.0.0` with guarded auth and secure PostgreSQL RLS required. This is safe only while the **host** publishes to `127.0.0.1`, as written in Compose. Never change Compose to `0.0.0.0:18082:8082`, attach to a public reverse proxy, or give this local demo real customer data. Database URLs, token hashes, internal service token and Gemini key are passed as runtime environment values; local Docker administrators can inspect container environment, so this is **not** production-grade secret management. Both containers are on a Docker network shared with the RAG DB. Treat the host and Docker daemon as trusted.

## 1. Install from the upgrade ZIP

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
git branch --show-current  # feat/deployment-cicd
unzip -o ~/Downloads/ElyraOps-Phase6-Deployment-CICD-upgrade.zip
python scripts/apply_deployment_phase6.py
```

The installer refuses to replace unknown/customized versions of six existing files and removes the temporary patch payload. It doesn't access private configuration or call external APIs.

## 2. Offline regression tests

```bash
env -u ELYRA_RAG_RLS_MODE -u ELYRA_LOCAL_COMPOSE -u ELYRA_SECURITY_MODE \
 -u ELYRA_ACCESS_TOKENS_JSON -u ELYRA_AGENT_TOKEN -u ELYRA_CASES_DATABASE_URL \
 -u ELYRA_RAG_DATABASE_URL -u ELYRA_RAG_TEST_DATABASE_URL \
 -u ELYRA_SECURE_RAG_LIVE_TEST -u ELYRA_RLS_LIVE_TEST \
 -u GEMINI_API_KEY -u OPENAI_API_KEY \
 python -m unittest discover -s tests -v
python -m compileall -q elyraops agent_service scripts/phase6_smoke.py
git diff --check
```

## 3. Start Docker Desktop and the app

Prerequisites: Docker Desktop running; existing Phase 4 Docker database reachable on `127.0.0.1:5447`; `.env.security` and `.env.rls` already exist and are ignored by Git. Your existing database role and RAG tables must have their RLS policies enabled; the wrapper tests this first. The database Compose project network is `elyraops-rag_default` by default. If yours is different, set `ELYRA_RAG_DOCKER_NETWORK` to the actual network name from `docker network ls` **before** running the wrapper.

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
bash scripts/phase6_local.sh up
```

The wrapper never prints your Gemini API key or database password. It may prompt for the Gemini key; paste privately, press Enter. The build can take a while on first run. It does **not** delete your previous PostgreSQL volume, migrate data or seed new embeddings. The existing local dashboards at 8082 and FastAPI 8091 are unaffected.

To inspect the result and verify endpoints **from inside the Compose network**:

```bash
bash scripts/phase6_local.sh check
```

To inspect container status or last 60 log lines:

```bash
bash scripts/phase6_local.sh ps
bash scripts/phase6_local.sh logs
```

Open **http://127.0.0.1:18082** and sign in with your previously generated local Analyst token (not the internal agent token). Create a new *synthetic* Billing case, investigate, verify `POL-001` and `Pending approval`, then use the Approver token for **Approve simulation**. The dashboard should show the existing PostgreSQL case records because Phase 6 connects to the same DB.

To shut down only the Phase 6 app containers:

```bash
bash scripts/phase6_local.sh down
```

Do NOT run `docker compose down -v`, delete volumes, rotate DB roles, publish an agent port, or initialize a new empty database. The original `docker-compose.rag.yml` remains the owner of the existing PostgreSQL data volume.

## 4. Optional read-only load smoke

If `k6` is installed on your Mac:

```bash
k6 run load/k6_phase6.js
```

This probes localhost dashboard health/config only (not authentication, database throughput, LLM throughput, or accuracy). Record actual latency measurements before claiming performance impact.

## 5. GitHub CI and merge

```bash
git status --short
git add Dockerfile.phase6 compose.phase6.yml DEPLOYMENT_PHASE6.md .dockerignore \
 docker-compose.yml .github/workflows/ci.yml elyraops/server.py elyraops/agent_client.py \
 scripts/phase6_local.sh scripts/phase6_smoke.py scripts/apply_deployment_phase6.py \
 tests/test_deployment_phase6.py tests/test_observability_phase5.py load/k6_phase6.js
git diff --cached --check
git diff --cached --name-only
git commit -m 'feat: add localhost-only Docker deployment and image smoke CI'
git -c http.version=HTTP/1.1 push -u origin feat/deployment-cicd
```

Open PR against `main`. Verify `test (3.12)`, `test (3.13)`, `secure-rag-postgres`, **and `phase6-docker-smoke`** are green. Merge via GitHub, then `git switch main && git pull origin main && git status -sb`.

**Not verified in the authoring environment:** the actual Docker image build and runtime Compose startup (Docker unavailable here). You must check on your Mac/GitHub CI. Local Python tests, shell/YAML syntax and static Compose assertions can be run before making any claim of deployment success.
