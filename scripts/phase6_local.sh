#!/usr/bin/env bash
# Local-only Compose helper. Never print secrets or publish any non-loopback ports.
set -euo pipefail
set +x
cd "$(dirname "$0")/.."

usage() { echo "Usage: bash scripts/phase6_local.sh {up|check|ps|logs|down}"; exit 2; }
MODE="${1:-}"
case "$MODE" in up|check|ps|logs|down) ;; *) usage ;; esac
command -v docker >/dev/null || { echo "Docker Desktop is required." >&2; exit 1; }

if [[ "$MODE" == "up" ]]; then
  [[ -f .env.security && -f .env.rls ]] || { echo "Missing .env.security or .env.rls. Complete Phases 3A/3B first." >&2; exit 1; }
  [[ -x .venv/bin/python ]] || { echo "Activate an existing .venv with PostgreSQL/RAG packages first." >&2; exit 1; }
  set -a
  # Trusted files created by the earlier local-only setup scripts; never echo contents.
  source .env.security
  source .env.rls
  set +a
  [[ "${ELYRA_SECURITY_MODE:-}" == "required" ]] || { echo "Guarded auth must be required." >&2; exit 1; }
  [[ -n "${ELYRA_ACCESS_TOKENS_JSON:-}" && -n "${ELYRA_AGENT_TOKEN:-}" && ${#ELYRA_AGENT_TOKEN} -ge 32 ]] || { echo "Missing guarded tokens." >&2; exit 1; }
  [[ -n "${ELYRA_CASES_DATABASE_URL:-}" ]] || { echo "Missing RLS runtime DB URL." >&2; exit 1; }
  export ELYRA_RAG_RLS_MODE=required

  # Keep the existing PostgreSQL volume and role in place. No destructive migrations.
  docker compose -f docker-compose.rag.yml up -d

  # Verify the RLS backend and secure RAG using the trusted local DB role first.
  .venv/bin/python - <<'PYCODE'
from elyraops import pg_cases
from agent_service.rag_pg import secure_rag_connection
pg_cases.verify_backend()
with secure_rag_connection('startup-probe') as conn:
    conn.execute('SELECT 1')
print('Case store and RAG RLS preflight succeeded (existing data unchanged).')
PYCODE

  # Compose joins the already-running db service on an external Docker network.
  # Rewrite ONLY the internal host/port; keep the encoded username/password unchanged.
  ELYRA_CASES_DATABASE_URL="$({ .venv/bin/python - <<'PYCODE'
import os
from urllib.parse import urlsplit, urlunsplit
raw=os.environ['ELYRA_CASES_DATABASE_URL']
p=urlsplit(raw)
if p.scheme not in {'postgresql', 'postgres'} or p.hostname not in {'127.0.0.1','localhost'} or p.port != 5447 or not p.username or not p.password:
    raise SystemExit('Expected the existing localhost:5447 RLS runtime URL; no Docker changes applied')
auth=p.netloc.rsplit('@',1)[0]
print(urlunsplit((p.scheme,auth+'@rag-db:5432',p.path,p.query,p.fragment)))
PYCODE
  } )"
  export ELYRA_CASES_DATABASE_URL
  if [[ -z "${GEMINI_API_KEY:-}" ]]; then
    echo 'Gemini key is needed for live semantic retrieval; paste it privately.'
    read -r -s -p 'Gemini API key: ' GEMINI_API_KEY
    echo
    export GEMINI_API_KEY
  fi
  [[ -n "${GEMINI_API_KEY:-}" ]] || { echo "Gemini key is required for the live investigation demo." >&2; exit 1; }
  docker compose -f compose.phase6.yml config --quiet
  docker compose -f compose.phase6.yml up --build -d
  echo 'Phase 6 dashboard is at http://127.0.0.1:18082 (localhost only).'
  echo 'Run: bash scripts/phase6_local.sh check'
  exit 0
fi

# No secrets needed to manage existing containers; placeholders only satisfy
# Compose's required-env parse step, never start any services with these values.
export ELYRA_CASES_DATABASE_URL='postgresql://elyra_cases_runtime:placeholder@rag-db:5432/elyra_rag'
export ELYRA_AGENT_TOKEN='placeholder-internal-token-do-not-start-services'
export ELYRA_ACCESS_TOKENS_JSON='placeholder-do-not-start-services'
case "$MODE" in
  check)
    docker compose -f compose.phase6.yml ps
    docker compose -f compose.phase6.yml exec -T elyra-agent python /app/scripts/phase6_smoke.py \
      --dashboard-url http://elyra-dashboard:8082 --agent-url http://127.0.0.1:8091 --require-guard
    ;;
  ps) docker compose -f compose.phase6.yml ps ;;
  logs) docker compose -f compose.phase6.yml logs --tail 60 ;;
  down) docker compose -f compose.phase6.yml down ;; # Never use --volumes.
esac
