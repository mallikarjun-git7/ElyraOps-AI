# ElyraOps AI phase 1 — Optional LangGraph + FastAPI service

**Status:** New runnable integration code. `agent_service` runs a *LangGraph* triage → local policy retrieval → constrained planning graph. If you provide an OpenAI API key, the planning node calls a real language model to draft a bounded recommendation explanation; without a key, the graph runs in clearly labeled deterministic demo mode. **Neither mode executes a business action.** The old dashboard still works without the add-on.

This is **NOT** a production multi-agent system: no persistent LangGraph checkpoints, no model-selected tool execution, no autonomous external side effects, and no production authentication, tenant isolation or vector database. Do not describe it as such.

## Start on macOS (Python 3.10+)

In the existing ElyraOps-AI repository on your `feat/agentic-ai` branch:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-agent.txt
python -m unittest discover -s tests -v
```

Set up **both** processes with the **same** SQLite path (by default the repo's `data/elyraops.db`). Keep both terminals in your repository root.

**Terminal A:**

```bash
source .venv/bin/activate
python -m uvicorn agent_service.app:app --host 127.0.0.1 --port 8091
```

**Terminal B:**

```bash
source .venv/bin/activate
export ELYRA_AGENT_URL=http://127.0.0.1:8091
python -m elyraops.server
```

Open `http://127.0.0.1:8080`, create a **new** case (cases already investigated will remain processed), and click **Start agent investigation**. The case audit log should show `langgraph` as the actor. Use this command to check the mode:

```bash
curl -s http://127.0.0.1:8091/health
```

### Enable real model-backed explanations (optional, billed by your provider)

In Terminal A, before launching uvicorn:

```bash
export OPENAI_API_KEY='paste-your-key-here'
export OPENAI_MODEL='gpt-4.1-mini'
python -m uvicorn agent_service.app:app --host 127.0.0.1 --port 8091
```

Never commit API keys to GitHub. Do not use real customer data in the demo. Model unavailability causes a `503` and leaves the case unchanged; no fabricated simulation fallback occurs after a failed provider request.

### Security limitations

* Both HTTP processes bind to localhost, with no user authentication. Do not expose them on public hosts or send real confidential data.
* `ELYRA_AGENT_TOKEN` optionally protects requests to the agent service (set an identical value in both terminals); this is not a substitute for end-user authorization.
* Two processes use one local SQLite database for a demo. Production requires a backend API boundary and a stronger database / tenant isolation.
* Policy text is treated as untrusted data. The model can only write a rationale, while allowed actions are enforced in code and remain behind human approval.
* All approvals continue to be **simulated**, with no external business side effects.

### Useful regression command

```bash
python -m unittest discover -s tests -v
```

The new offline tests pass without FastAPI/LangGraph installed. The actual API+LangGraph integration requires the above packages and a runtime smoke test; this should be checked locally before merging your branch.
