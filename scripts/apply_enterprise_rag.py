"""Idempotent update of existing ElyraOps files. Run from repository root."""
from pathlib import Path


def replace_once(data: str, old: str, new: str, path: str) -> str:
    if new in data:
        return data
    if data.count(old) != 1:
        raise SystemExit(f"Refusing to modify {path}: expected patch anchor missing or duplicated")
    return data.replace(old, new, 1)


core_path = Path("elyraops/core.py")
workflow_path = Path("agent_service/workflow.py")
app_path = Path("agent_service/app.py")
for path in (core_path, workflow_path, app_path):
    if not path.exists():
        raise SystemExit(f"Run inside ElyraOps-AI repository root: missing {path}")

core = core_path.read_text()
old = '    docs = [dict(x) for x in db.execute("SELECT * FROM knowledge")]'
new = '''    # Only policies for the case domain may be cited; keyword overlap does not
    # confer document access or business relevance.
    docs = [dict(x) for x in db.execute("SELECT * FROM knowledge WHERE domain=?", (domain,))]'''
core = replace_once(core, old, new, str(core_path))

workflow = workflow_path.read_text()
workflow = replace_once(workflow,
    'from .provider import draft_rationale',
    'from .provider import draft_rationale\nfrom .rag_pg import retrieve_for_case', str(workflow_path))
workflow = replace_once(workflow,
    '    with core.connect() as db:\n        evidence=core.retrieve(db, case["title"]+" "+case["description"], state["domain"])',
    '    evidence=retrieve_for_case(case)', str(workflow_path))

app = app_path.read_text()
app = replace_once(app, 'from .provider import ModelUnavailable',
                   'from .provider import ModelUnavailable\nfrom .rag_pg import RagUnavailable', str(app_path))
app = replace_once(app,
    '    except ModelUnavailable:\n        raise HTTPException(503,"AI provider unavailable; case unchanged")',
    '    except ModelUnavailable:\n        raise HTTPException(503,"AI provider unavailable; case unchanged")\n    except RagUnavailable:\n        raise HTTPException(503,"RAG retrieval unavailable; case unchanged")', str(app_path))

for path, data in ((core_path, core), (workflow_path, workflow), (app_path, app)):
    if path.read_text() != data:
        path.write_text(data)
        print("Updated", path)
print("Phase 2 patch applied. Offline behavior remains available by default.")
