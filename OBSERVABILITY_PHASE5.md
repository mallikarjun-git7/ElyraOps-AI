# ElyraOps AI — Phase 5: reliability and observability (local demonstration)

This upgrade leaves the human-approval workflow and PostgreSQL tenant RLS rules intact. It adds:

- **JSON request logs**, for dashboard and FastAPI, with bounded route names, HTTP status, timing and correlation IDs. No bodies, full URLs, credentials, tenant names, case IDs or policy text are logged.
- **`X-Request-ID`** on both services, and propagation across the dashboard → FastAPI request. Arbitrary IDs are rejected; only 32-hex-character IDs are accepted, or generated anew.
- **`GET /metrics`** on dashboard and FastAPI, exposing bounded-label request counters and duration histograms in Prometheus text format. In guarded mode, require the internal agent token. Each service reports **its own process-local** measurements; counters reset after restart.
- **`GET /ready`** on FastAPI to check configured PostgreSQL case and secure RAG connections without calling an LLM. `GET /health` remains the cheap process-liveness endpoint.
- **Bounded agent-client timeout** `ELYRA_AGENT_TIMEOUT_SECONDS` (5–120, default 60). State-changing `POST /v1/investigate` is **not retried automatically**.
- **LangGraph stage timing logs**, limited to fixed stage names. Correlation IDs are best-effort when LangGraph runs nodes on separate threads.
- **Read-only k6 smoke test** for localhost `/health` and `/ready`; the script does not generate investigation or approval requests.

This is not a production observability stack: there is no OpenTelemetry collector, distributed span store, managed alerting, SLA guarantee, durable telemetry, or multi-worker aggregation. Logs should not be forwarded off-device without a privacy review.

## 1 — Install on the Phase 5 branch

```bash
cd ~/Downloads/ElyraOps-AI
git branch --show-current         # feat/observability-reliability
unzip -o ~/Downloads/ElyraOps-Phase5-Observability-Reliability-upgrade.zip
python3 scripts/apply_observability_phase5.py
```

The installer verifies the unchanged Phase 4 source files before replacing them. It refuses unexpected source edits rather than silently overwriting them. The upgrade requires **no database migration, no model API calls, and no Docker volume changes**.

## 2 — Run tests without secrets or live services

```bash
source .venv/bin/activate
env -u ELYRA_RAG_RLS_MODE -u ELYRA_SECURITY_MODE -u ELYRA_ACCESS_TOKENS_JSON \
  -u ELYRA_AGENT_TOKEN -u ELYRA_CASES_DATABASE_URL -u ELYRA_RAG_DATABASE_URL \
  -u ELYRA_RAG_TEST_DATABASE_URL -u ELYRA_SECURE_RAG_LIVE_TEST -u ELYRA_RLS_LIVE_TEST \
  -u GEMINI_API_KEY -u OPENAI_API_KEY \
  python -m unittest discover -s tests -v
python -m compileall -q agent_service elyraops
```

The new tests also cover metrics authorization, request-ID correlation, refusal of arbitrary IDs, timeout validation, client non-retry, readiness behavior, and scrubbed logs. Optional live PostgreSQL integration tests continue to run under your existing configuration and in GitHub CI.

## 3 — Restart agent and dashboard

In the **FastAPI** Terminal, stop the old process with Control+C and run:

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
set -a
source .env.security
source .env.rls
set +a
export ELYRA_RAG_RLS_MODE=required
unset ELYRA_RAG_DATABASE_URL
unset ELYRA_RLS_ADMIN_DATABASE_URL
export ELYRA_AGENT_TIMEOUT_SECONDS=60
read -s 'GEMINI_API_KEY?Paste Gemini key: '; echo; export GEMINI_API_KEY
python -m uvicorn agent_service.app:app --host 127.0.0.1 --port 8091
```

In the **Dashboard** Terminal, stop the old process and run:

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
set -a
source .env.security
source .env.rls
set +a
export ELYRA_AGENT_URL=http://127.0.0.1:8091
export ELYRA_AGENT_TIMEOUT_SECONDS=60
export PORT=8082
python -m elyraops.server
```

Both services must stay bound to loopback (`127.0.0.1`). Avoid deploying this local demo on a public IP.

## 4 — Verify health, readiness, correlation and protected metrics

In a separate Terminal:

```bash
curl -i http://127.0.0.1:8091/health
curl -i http://127.0.0.1:8091/ready
curl -i http://127.0.0.1:8082/health
```

`/ready` returns `503` if a required PostgreSQL role, schema or policy check fails. It does **not** verify the Gemini provider or approval API. The `X-Request-ID` response header should be present on both services.

If you have loaded `.env.security` in this Terminal, read metrics without putting the token in the command-line argument list:

```bash
set -a; source .env.security; set +a
printf 'header = "X-Agent-Token: %s"\n' "$ELYRA_AGENT_TOKEN" | curl -fsS --config - http://127.0.0.1:8091/metrics | head -30
printf 'header = "X-Agent-Token: %s"\n' "$ELYRA_AGENT_TOKEN" | curl -fsS --config - http://127.0.0.1:8082/metrics | head -30
```

Do not copy the token or your `.env` files into screenshots, issues, commits, or chat messages.

Create a synthetic Billing case and investigate it. Observe the **same request ID** in the dashboard and FastAPI JSON request log lines; the response remains approval-gated and should cite `POL-001` as before. Stage logs omit the case title and raw LLM response.

## 5 — Optional read-only performance smoke

Install `k6` separately if desired (`brew install k6`). With both services running:

```bash
k6 run load/k6_smoke.js
```

Default: 5 virtual users over 15 seconds, using only the FastAPI `/health` and `/ready` endpoints on localhost:8091. Thresholds in the script are **developer smoke-test gates**, not a claimed production SLA. `/ready` checks configured databases and may be slower than `/health`. Do not run this test against production or an internet-exposed instance.

## 6 — Commit and review

```bash
git status --short
git diff --check
git add OBSERVABILITY_PHASE5.md load/k6_smoke.js \
  elyraops/observability.py elyraops/server.py elyraops/agent_client.py \
  agent_service/app.py agent_service/workflow.py \
  scripts/apply_observability_phase5.py tests/test_observability_phase5.py
git diff --cached --check
git diff --cached --name-only
git commit -m 'feat: add structured observability and reliability controls'
git -c http.version=HTTP/1.1 push -u origin feat/observability-reliability
```

Review GitHub CI and open a PR only after tests and the end-to-end local demo pass. **Never stage `.env.security`, `.env.rls`, `.env.login-tokens`, database URLs containing passwords, or API keys.**

## Next improvements

Actual OpenTelemetry spans + collector, end-to-end retry/idempotency strategy, queue-based workflow scheduling, configurable alert rules, load testing on controlled ephemeral environments and log retention/rotation. Production identity and deployment require separate hardening.
