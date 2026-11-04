# ElyraOps Phase 2 — Retrieval quality + optional PostgreSQL/pgvector

**This is an incremental local development upgrade, not production-ready enterprise authorization.**

The patch fixes the original keyword retrieval: billing cases no longer cite unrelated damaged-delivery or procurement documents. Optional hybrid retrieval uses actual Gemini Embedding 001 vectors in pgvector, PostgreSQL full-text search, and reciprocal rank fusion (RRF). The case-management database remains SQLite. The same LangGraph model-backed explanation and human-gated *simulation* are retained.

## A. Apply and verify the safe offline improvement

From the `feat/enterprise-rag` branch at the repository root:

```bash
unzip -o ~/Downloads/ElyraOps-Enterprise-RAG-upgrade.zip
python3 scripts/apply_enterprise_rag.py
source .venv/bin/activate
python -m unittest discover -s tests -v
```

Without `ELYRA_RAG_DATABASE_URL`, the app **continues to use local SQLite** with stricter domain filtering. Restart the running FastAPI service to load the new implementation. Previously investigated cases keep their historical evidence; make a new case to see new retrieval.

## B. Activate the real pgvector hybrid backend (optional)

This intentionally runs on **localhost:5447**, avoiding other local PostgreSQL containers on 5432/5433.

```bash
docker compose -f docker-compose.rag.yml up -d
python -m pip install -r requirements-rag.txt
export ELYRA_RAG_DATABASE_URL=postgresql://elyra_demo:elyra_demo_pw_change_for_real_use@127.0.0.1:5447/elyra_rag
python -m agent_service.rag_pg seed
```

Set the existing Gemini key privately *in this Terminal* before running the seed command (for example with `read -s 'GEMINI_API_KEY?Gemini key: '; echo; export GEMINI_API_KEY`). Seeding makes several requests to the Gemini embedding endpoint and may use free-tier quota. No embedding request is made without the key. The repository never stores the key.

The pgvector-only service is not exposed on the public internet. The demo database password is illustrative; change it before using non-demo data.

To activate hybrid retrieval in **Terminal A (agent service)**:

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
export ELYRA_RAG_DATABASE_URL=postgresql://elyra_demo:elyra_demo_pw_change_for_real_use@127.0.0.1:5447/elyra_rag
# Ensure GEMINI_API_KEY is set privately in Terminal A.
python -m uvicorn agent_service.app:app --host 127.0.0.1 --port 8091
```

Keep **Terminal B** unchanged (`ELYRA_AGENT_URL=http://127.0.0.1:8091`, `PORT=8082`, `python -m elyraops.server`). Create a new Billing case and investigate it. Both LLM and embedding API requests consume provider quota. The system fails closed with 503 if PostgreSQL or embeddings are unavailable—no case update is committed. Unset `ELYRA_RAG_DATABASE_URL` and restart FastAPI to return to safe local keyword retrieval.

## C. Ingest an original policy document from your Mac

Plain text or Markdown only; under 120 KB:

```bash
python -m agent_service.rag_pg ingest --file docs/policy.md --id POL-200 --title 'Billing escalation policy' --domain Billing --tenant shared
```

For a demo organization-specific document, pass `--tenant 'Demo Commerce'` instead of `shared`. Note: organization is user-supplied in today's demo, not an authenticated tenant identity.

## D. Opt-in real Postgres integration smoke test

```bash
export ELYRA_RAG_TEST_DATABASE_URL="$ELYRA_RAG_DATABASE_URL"
python -m unittest discover -s tests -v
```

Requires the seeded DB and an active Gemini key; it sends a real embedding request. Omit `ELYRA_RAG_TEST_DATABASE_URL` for offline CI that skips the live test.

## Security and scalability limitations

- **Not production multi-tenancy:** user-editable case organization values are not trustworthy. True tenant authorization requires verified OIDC identity, backend access control, and DB-level RLS. The current label filter only illustrates data scoping.
- No authenticated ingestion API; files are ingested manually from a trusted local terminal.
- No untrusted document import, PDF parsing, automatic deletion or lifecycle governance yet.
- Real embedding calls transmit text to the Gemini API; use synthetic documents only on free tier.
- pgvector is a *knowledge index only*. Case records, approvals, and audit traces remain in SQLite until a later migration.
- No absolute performance/accuracy claim: evaluate retrieval using test queries and a held-out data set before describing results on a résumé.

Reference specifications:
- https://github.com/pgvector/pgvector#hybrid-search
- https://ai.google.dev/gemini-api/docs/embeddings
