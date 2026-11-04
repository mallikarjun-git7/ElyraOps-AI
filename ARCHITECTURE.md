# Architecture and design decisions

## Current implemented architecture (v0.1)

```
Browser (HTML + vanilla JS)
   |
   | JSON REST, same origin
   v
Python ThreadingHTTPServer (elyraops/server.py)
   |
   v
Core workflow state machine (elyraops/core.py)
   |-- Case creation + investigation
   |-- Policy document retrieval (local transparent keyword scorer)
   |-- Approval gate (demo operator name only; NOT authorization)
   |-- Simulation-only execution event
   v
SQLite case / knowledge / append-style event tables
```

## Why human approval is mandatory

LLM output is untrusted and must never constitute authorization. For a real product, validation and execution must happen in a separate secured service, with server-side identity checks, policy decisions, replay protection, and audit trails.

## Meaning of "agent" in this starter

The sample uses three deterministic orchestration steps named `triage_agent`, `retrieval_agent`, `resolution_agent` to demonstrate state transitions and traces. They are **not autonomous language-model agents**. Actual model integration is a roadmap deliverable.

## Target architecture (unimplemented)

```
Next.js UI + OIDC
   |
Spring Boot REST + Policy + Outbox ---- PostgreSQL / pgvector
   |                                    |
Kafka event bus ------------------ async consumers
   |
FastAPI / LangGraph agents --- MCP tool gateway --- approved business APIs
   |
Eval suites + traces + Langfuse + OpenTelemetry
```

## Security gaps to close before any public deployment

- Real OIDC session authentication and authorization on every API route
- Input request limits and API rate limiting behind a reverse proxy
- Tenant isolation with database-enforced row-level restrictions
- Permission-aware knowledge search and encrypted data storage
- CSRF protection for browser session mutation, if cookie authentication is used
- Secret and configuration management, audit retention, backups and restoration
- Static-analysis and dependency scanning, abuse tests, prompt injection evaluation
- Never permit production money movement from an LLM recommendation alone

## Test quality and evidence

`tests/test_workflows.py` verifies state transitions, retrieval, idempotency, approval and rejection. It does not claim performance, scale, uptime, availability, threat resistance or AI accuracy. Collect reproducible metrics before including them on a résumé.
