# ElyraOps AI

**Enterprise Agentic Operations Platform** — an original, working **simulation-mode** portfolio prototype with a warm ivory/cream interface, evidence-backed triage, approval-gated recommendations, persistent case records, and traceable event history.

> **Implementation status:** The default dashboard is a *local deterministic workflow simulator*. An optional LangGraph + FastAPI service (`agent_service/`) provides a genuine workflow graph and can call an LLM for the rationale when a model API key is configured. It does **not** implement autonomous business actions, vector RAG, a Java microservice, Kafka, production auth, or production deployment. Those features are in the roadmap. No payment is issued; no external business system is changed. Never use real customer records in this demo.

## Optional LangGraph + FastAPI extension

See [AGENTIC_PHASE1.md](AGENTIC_PHASE1.md) for a two-terminal local setup. **Without `ELYRA_AGENT_URL`, the existing app remains a simulation.** With the agent service connected and an API key configured, it uses an LLM only for a constrained, evidence-grounded explanation; approval and simulated execution remain unchanged.

## Screens and behavior

- Creamy-white responsive overview dashboard, case operations, knowledge hub, and workflow activity.
- Five seeded incidents across Billing, Logistics, Identity, Procurement and Support.
- Multi-stage *simulated* agent workflow: classifier → retrieval → resolution planner.
- Transparent local TF-IDF-like keyword policy retrieval, with evidence references and scores.
- Human approval/rejection before **simulated execution**.
- Persistent SQLite case and audit-event store. Re-running a submitted investigation does not duplicate actions.
- Create realistic custom cases and investigate them from the browser.

## Run locally (no installs beyond Python)

Requirements: Python 3.10+

```bash
python3 -m elyraops.server
```

Open **http://127.0.0.1:8080**. Investigation, approval, case creation and navigation work without a model API key. This demo makes no external requests.

Use `PORT=8090 python3 -m elyraops.server` to select another port. The default app binds to `127.0.0.1` deliberately.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Docker deployment (for demos, not public customer data)

```bash
docker compose up --build -d
curl http://localhost:8080/health
```

Docker uses a named volume for the SQLite database. **Important:** This demonstration has **no authentication** or per-tenant authorization. Docker exposes port 8080; run behind private access controls or on your own trusted local machine. Do *not* expose it publicly until those controls are implemented.

## HTTP API

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Health check |
| GET | `/api/dashboard` | Summary counts |
| GET | `/api/cases` | Cases |
| POST | `/api/cases` | Create demo case |
| GET | `/api/cases/EC-1042` | Case, evidence, audit events |
| POST | `/api/cases/EC-1042/investigate` | Deterministic multi-stage investigation |
| POST | `/api/cases/EC-1042/decision` | Record approved simulation or rejection |
| GET | `/api/knowledge` | Source policy documents |

Example:

```bash
curl -s -X POST http://localhost:8080/api/cases/EC-1042/investigate -H 'Content-Type: application/json' -d '{}'
curl -s http://localhost:8080/api/cases/EC-1042
curl -s -X POST http://localhost:8080/api/cases/EC-1042/decision -H 'Content-Type: application/json' -d '{"decision":"approve","actor":"Demo operator"}'
```

## Engineering roadmap for SDE-quality flagship

Each phase requires code, tests, measured results, and deployment verification before being described as completed:

1. **Production-grade Java service:** Spring Boot 4, PostgreSQL, Spring Security / OIDC, tenant isolation, REST contract and transactional outbox.
2. **Real agent service:** FastAPI and LangGraph with real LLM tool use, schema validation, persistent workflow checkpoints, evidence citations, and human-in-the-loop interruptions.
3. **Enterprise RAG:** document processing, permission-aware hybrid search, pgvector, citations, evaluation datasets, and adversarial prompt-injection tests.
4. **Distributed orchestration:** Kafka events, consumer retries, dead-letter queues, idempotency keys, outbox relay, and realistic concurrent integration tests.
5. **Governed external actions:** mock billing, logistics and IT ticket APIs; tool allowlists, OIDC role checks, approvals, policy enforcement, and audit integrity.
6. **Reliability and deployment:** OpenTelemetry, Langfuse, Prometheus, Grafana, k6, Testcontainers, CI/CD, AWS deployment and recovery drills.

See [ARCHITECTURE.md](ARCHITECTURE.md) for implementation decisions and [ORIGINS.md](ORIGINS.md) for attribution policy and optional DocsGPT integration.

## Current tech stack

**Python standard library, SQLite, HTML/CSS/JavaScript, Docker, GitHub Actions** for the default demo, with optional **FastAPI, LangGraph, and OpenAI API** integration. These are *implemented*, not aspirational. The advanced stack above is the intended target for subsequent development.

## Repository ownership

This prototype's application code was created independently for this deliverable, and is not a disguised DocsGPT clone. If you include original DocsGPT source as a dependency or derivative, preserve all MIT notices and credit upstream. Do not claim that original upstream code was independently authored.
