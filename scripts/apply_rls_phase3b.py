"""One-time Phase 3B wiring for ElyraOps AI, preserving SQLite default mode."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent


def patch(path, replacements):
    f = ROOT / path
    content = f.read_text()
    changed = False
    for before, after in replacements:
        if after in content:
            continue
        n=content.count(before)
        if n != 1:
            raise SystemExit(f'Expected exactly one patch anchor in {path} (got {n}): {before[:70]!r}. No update saved for this file.')
        content=content.replace(before,after,1)
        changed=True
    if changed:
        f.write_text(content)
        print('Updated '+path)
    else:
        print('Already updated '+path)


patch('elyraops/core.py', [
    ('from pathlib import Path\n', 'from pathlib import Path\nfrom . import pg_cases\n'),
    ('def initialize():\n    with transaction() as db:',
     'def initialize():\n    if pg_cases.enabled():\n        pg_cases.verify_backend()\n    with transaction() as db:'),
    ('def list_cases(organization=None):\n    with connect() as db:',
     'def list_cases(organization=None):\n    if pg_cases.enabled():\n        return pg_cases.list_cases(organization)\n    with connect() as db:'),
    ('def get_case(case_id, organization=None):\n    with connect() as db:',
     'def get_case(case_id, organization=None):\n    if pg_cases.enabled():\n        return pg_cases.get_case(case_id, organization)\n    with connect() as db:'),
    ('def investigate(case_id, organization=None):\n    with transaction() as db:',
     'def investigate(case_id, organization=None):\n    if pg_cases.enabled():\n        return pg_cases.investigate(case_id, organization)\n    with transaction() as db:'),
    ('    if not actor or not isinstance(actor, str) or len(actor) > 80:\n        raise ValueError("A short approver name is required")\n    with transaction() as db:',
     '    if not actor or not isinstance(actor, str) or len(actor) > 80:\n        raise ValueError("A short approver name is required")\n    if pg_cases.enabled():\n        return pg_cases.decide(case_id, decision, actor, organization)\n    with transaction() as db:'),
    ('    case_id = "EC-" + str(uuid.uuid4().int % 900000 + 100000)\n',
     '    if pg_cases.enabled():\n        return pg_cases.create_case({"title":title,"description":description,"domain":domain,"priority":priority},organization)\n    case_id = "EC-" + str(uuid.uuid4().int % 900000 + 100000)\n'),
])

patch('agent_service/app.py', [
    ('from elyraops import core, security\n', 'from elyraops import core, security, pg_cases\n'),
    ('from fastapi import FastAPI, Header, HTTPException\n', 'from fastapi import FastAPI, Header, HTTPException\nfrom fastapi.responses import JSONResponse\n'),
    ('app=FastAPI(title="ElyraOps Agent Service",version="0.2.0")\n', 'app=FastAPI(title="ElyraOps Agent Service",version="0.2.0")\n\n@app.exception_handler(pg_cases.CaseStoreUnavailable)\nasync def pg_cases_unavailable(_request, _exc):\n    return JSONResponse({"detail":"PostgreSQL case store unavailable"}, status_code=503)\n'),
    ('    run_id=str(uuid.uuid4())\n    # Never keep a DB write lock open while waiting for model calls.\n',
     '    if pg_cases.enabled():\n        try:\n            return pg_cases.commit_graph_result(payload.case_id, payload.organization, result)\n        except KeyError:\n            raise HTTPException(404,"Case not found")\n        except pg_cases.CaseStoreUnavailable:\n            raise HTTPException(503,"PostgreSQL case store unavailable")\n    run_id=str(uuid.uuid4())\n    # Never keep a DB write lock open while waiting for model calls.\n'),
])

patch('elyraops/server.py', [
    ('from . import security\n', 'from . import security\nfrom . import pg_cases\n'),
    ('    def do_GET(self):\n', '    def do_GET(self):\n        try:\n            return self._do_GET()\n        except pg_cases.CaseStoreUnavailable:\n            return self.write_json({"error": "PostgreSQL case store unavailable"}, 503)\n\n    def _do_GET(self):\n'),
    ('        except agent_client.AgentUnavailable as exc:\n            return self.write_json({"error": str(exc)}, 502)',
     '        except pg_cases.CaseStoreUnavailable:\n            return self.write_json({"error": "PostgreSQL case store unavailable"}, 503)\n        except agent_client.AgentUnavailable as exc:\n            return self.write_json({"error": str(exc)}, 502)'),
])

print('Phase 3B wiring applied. PostgreSQL case mode is OFF unless ELYRA_CASES_DATABASE_URL is set.')
