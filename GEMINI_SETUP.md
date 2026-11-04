# ElyraOps Gemini integration — Phase 1 add-on

For your existing `feat/agentic-ai` branch. This upgrade adapts the existing provider to the **Gemini OpenAI-compatible Chat Completions** endpoint. It does not add new agents or autonomous tool use; existing LangGraph runs with model-generated explanations. OpenAI stays available as a fallback provider when Gemini is not configured.

## Apply

Unzip this archive **into the repository root** (where `agent_service/` exists), then:

```bash
python3 scripts/apply_gemini_upgrade.py
source .venv/bin/activate
python -m unittest discover -s tests -v
```

## Configure and start (Terminal A)

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
unset OPENAI_API_KEY
read -s 'GEMINI_API_KEY?Paste Gemini key: '
echo
export GEMINI_API_KEY
export GEMINI_MODEL=gemini-3.5-flash-lite
python -m uvicorn agent_service.app:app --host 127.0.0.1 --port 8091
```

If another server is already on 8091, stop it gracefully first. The key is not written to disk or GitHub. Keep Terminal A open.

## Main backend (Terminal B)

```bash
cd ~/Downloads/ElyraOps-AI
source .venv/bin/activate
export ELYRA_AGENT_URL=http://127.0.0.1:8091
export PORT=8082
python -m elyraops.server
```

If main backend is already correctly running on 8082, no need to restart it.

## Verify

```bash
curl -s http://127.0.0.1:8091/health
```

Expect `"llm_provider":"gemini"` and `"llm_enabled":true`. Next create a **new synthetic case** from the dashboard and run the investigation. `langgraph-llm` in the audit event means a model-generated explanation was received. Approval is still simulated only.

Free-tier usage is model/project dependent, subject to quotas, and free-tier content may be used by the provider to improve its products. Never send real sensitive customer data. `503` after a real call means inspect your API key, model availability, quotas, and the Uvicorn logs (do not share credentials).

Docs: https://ai.google.dev/gemini-api/docs/openai and https://ai.google.dev/gemini-api/docs/pricing
