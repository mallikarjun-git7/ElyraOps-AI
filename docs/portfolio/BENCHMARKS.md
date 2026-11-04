# ElyraOps AI — reproducible k6 benchmark protocol

**Scope:** read-only local dashboard smoke measurements. This test requests only `GET /health` and `GET /api/auth/config` (no credentials). **It does not measure case-store SQL throughput, pgvector retrieval, agent/LLM inference, business-action writes or complete request-to-approval latency.**

## Run with an already healthy local deployment

Prerequisites: `k6` installed locally, Docker Compose dashboard at `http://127.0.0.1:18082` and `bash scripts/phase6_local.sh check` passing.

```bash
cd ~/Downloads/ElyraOps-AI
mkdir -p data/benchmarks
k6 run --summary-export=data/benchmarks/phase7-summary.json load/k6_portfolio.js
python scripts/phase7_benchmark_report.py \
  --summary data/benchmarks/phase7-summary.json \
  --output data/benchmarks/phase7-report.md \
  --environment 'Local Docker Desktop; operator-recorded hardware'
```

Open `data/benchmarks/phase7-report.md`. It is a **measured report** only after you run k6. The `data/` directory is Git-ignored, so raw outputs and any locally sensitive context will not be committed accidentally.

Default load: **5 virtual users for 20 seconds**. Optional knobs are `ELYRA_K6_VUS` (1–20), `ELYRA_K6_DURATION` (5–120 seconds, whole seconds), and `ELYRA_K6_BASE_URL` (localhost `18082` only). The script fails immediately if the target is non-local or if either knob is outside the safe bounds.

## Interpretation and limitations

- `http_req_duration` reports HTTP request latency **in milliseconds**, including local response handling. Record p50, p90, p95 and the request count from the k6 JSON; never fabricate them.
- `http_req_failed` is the proportion of failed HTTP requests; `checks` tracks whether expected status codes were observed.
- Thresholds (`http_req_failed < 1%`, `p95 < 1000ms`) are **test assertions**, not guaranteed or validated production SLOs.
- State Mac model/CPU, Docker Desktop settings, background load, exact commit SHA and k6 version in a report you elect to publish. Repeat after warmup if making comparisons, and report variation instead of a single cherry-picked run.
- The benchmark does not require tokens and sends no case content. The report generator never reads `.env.*` files.
- Do not claim a percentage speedup without a measured, comparable baseline, or describe the result as realistic peak transaction throughput.

## Evidence to publish

The app's verified local Docker workflow and CI checks can be demonstrated independently of this benchmark. To publish performance numbers in a résumé or GitHub README, copy a reviewed, sanitized measured report into `docs/portfolio/` (not the raw JSON unless you deliberately want it public), cite the test environment and workload, and state the limited endpoint scope.
