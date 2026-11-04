# ElyraOps AI — measured local HTTP smoke benchmark

> **Workload limitation:** Only dashboard `GET /health` and `GET /api/auth/config` on localhost:18082. Does NOT benchmark SQL, pgvector, LangGraph, Gemini, case writes, approvals or end-to-end latency.

- Report generated: 2026-11-04 14:31 UTC
- Environment (operator supplied): macOS Docker Desktop; k6 v2.3.0; 5 VUs; 20s; single run; warmup not recorded
- Source commit (operator supplied): d535fb7
- Workload: bounded read-only k6 script `load/k6_portfolio.js`

| Metric | Actual k6 value |
| --- | ---: |
| HTTP requests | 550 |
| HTTP error rate | 0.00% |
| Successful checks (ratio) | 100.00% |
| Request latency p50 | 5.98 ms |
| Request latency p90 | 10.76 ms |
| Request latency p95 | 12.04 ms |
| Request latency max | 15.95 ms |

## Configured threshold checks

Passing the thresholds is not evidence of a production SLA.

- The k6 summary did not report threshold results; no pass/fail claim made.

## Before publishing

Record k6 version, Mac hardware, Docker Desktop resources, repetition count, warmup policy and background load. Preserve the bounded endpoint scope. Do not claim a speedup without comparable baseline measurements.
