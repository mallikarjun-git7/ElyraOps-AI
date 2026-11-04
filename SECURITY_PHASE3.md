# ElyraOps AI — Phase 3A: guarded local HTTP API

This upgrade adds a **local-only opt-in guarded mode**. It is **not** a production identity platform. Keep all services on `127.0.0.1`, use only synthetic records, and do not expose them to the internet.

## Security model

- The main HTTP server authenticates `Authorization: Bearer ...` tokens. Only SHA-256 token digests are stored in the local `.env.security` file (except a random internal service secret). Tokens are generated using Python's `secrets` module and compared using `hmac.compare_digest`.
- Users have exactly one organization. API reads and writes are explicitly scoped to that organization; the tenant is **never trusted from user-submitted case JSON**. Cross-tenant lookups return 404.
- `viewer`: read own cases and shared knowledge; `analyst`: read, create, investigate; `approver`: read, approve/reject; `admin`: all actions for their own organization.
- In guarded mode, approval actor is always the authenticated user, not the submitted name.
- Agent service requires a distinct random `X-Agent-Token` (at least 32 characters) and a trusted organization in the **internal-only** API call. It double-checks organization within its write transaction.
- Unguarded mode is preserved solely for backwards compatibility of the earlier demo. **It is not protected.**
- PostgreSQL RAG retains its existing shared/organization labels. Those are NOT PostgreSQL row-level security, and its administrative CLI is trusted local only. The case store remains SQLite.

## One-time setup

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
python scripts/dev_auth.py --organization 'Synthetic Organization'
```

Keep the printed tokens private. The generated `.env.security` file is excluded from Git and has owner-only permissions. You can generate only once; to rotate credentials, stop the services, carefully replace the file and restart both processes. In secure mode, seeded cases belong to **other** demo organizations: create new cases under `Synthetic Organization` instead.

## Start agent service (Terminal A)

Stop the currently running agent service first (Ctrl+C). Then:

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
source .env.security
export ELYRA_RAG_DATABASE_URL='postgresql://elyra_demo:elyra_demo_pw_change_for_real_use@127.0.0.1:5447/elyra_rag'
read -s 'GEMINI_API_KEY?Paste Gemini API key: '; echo; export GEMINI_API_KEY
python -m uvicorn agent_service.app:app --host 127.0.0.1 --port 8091
```

## Start dashboard (Terminal B)

Stop the currently running dashboard first (Ctrl+C). Then:

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
source .env.security
export ELYRA_AGENT_URL=http://127.0.0.1:8091
export PORT=8082
python -m elyraops.server
```

Open `http://127.0.0.1:8082` and paste the **analyst** or **admin** token into the login screen. The token remains in browser memory and is not saved to localStorage or sent in URLs. Refreshing the browser requires entering it again. Use the **approver** token to review pending cases; only admin can both investigate and approve. **Use two browser sessions (e.g. private window) to test separate roles.**

## Tests

Run offline tests without your live service variables (the new security tests enable guarded mode internally):

```bash
env -u ELYRA_SECURITY_MODE -u ELYRA_ACCESS_TOKENS_JSON -u ELYRA_AGENT_TOKEN -u GEMINI_API_KEY -u OPENAI_API_KEY -u ELYRA_RAG_DATABASE_URL -u ELYRA_RAG_TEST_DATABASE_URL python -m unittest discover -s tests -v
```

## Limitations and production migration

This implements a **functional server-side demo security layer**, not OIDC or a user-management platform. A real service still requires managed OIDC, PKCE, MFA, short-lived sessions, TLS, rate limiting, formal tenant IDs and memberships, central audit controls, secure secrets management, PostgreSQL cases, RLS with non-owner roles, CSRF/session design where relevant, and deployment hardening. Do not call this production-ready, or claim that PostgreSQL RLS was implemented.
