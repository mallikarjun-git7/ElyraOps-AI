"""Patch ElyraOps Phase 1 branch to support Gemini OpenAI-compatible REST API.

Run from repository root: python3 scripts/apply_gemini_upgrade.py

Intentionally fails closed if expected source anchors differ, and modifies only
three small integration points. Does not read/store API secrets.
"""
from pathlib import Path

root = Path(__file__).resolve().parent.parent

changes = {
    "agent_service/provider.py": [
        (
            '    key = os.environ.get("OPENAI_API_KEY", "").strip()\n'
            '    if not key:\n'
            '        raise ModelUnavailable("OPENAI_API_KEY is not configured")\n'
            '    model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")',
            '    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()\n'
            '    key = gemini_key or os.environ.get("OPENAI_API_KEY", "").strip()\n'
            '    if not key:\n'
            '        raise ModelUnavailable("Neither GEMINI_API_KEY nor OPENAI_API_KEY is configured")\n'
            '    model = (os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")\n'
            '             if gemini_key else os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"))\n'
            '    endpoint = ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"\n'
            '                if gemini_key else "https://api.openai.com/v1/chat/completions")'
        ),
        (
            '        "https://api.openai.com/v1/chat/completions",\n'
            '        data=json.dumps(payload).encode("utf-8"),',
            '        endpoint,\n'
            '        data=json.dumps(payload).encode("utf-8"),'
        ),
    ],
    "agent_service/workflow.py": [
        (
            '    if os.environ.get("OPENAI_API_KEY", "").strip():',
            '    if os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip():'
        ),
    ],
    "agent_service/app.py": [
        (
            '    return {"status":"ok", "service":"elyraops-agents", "llm_enabled":bool(os.environ.get("OPENAI_API_KEY"))}',
            '    gemini = bool(os.environ.get("GEMINI_API_KEY", "").strip())\n'
            '    openai = bool(os.environ.get("OPENAI_API_KEY", "").strip())\n'
            '    return {"status":"ok", "service":"elyraops-agents",\n'
            '            "llm_enabled":gemini or openai,\n'
            '            "llm_provider":"gemini" if gemini else ("openai" if openai else "demo")}'
        ),
    ],
}

# Verify all anchors before modifying any file.
prepared = {}
for relpath, replacements in changes.items():
    path = root / relpath
    if not path.is_file():
        raise SystemExit(f"Missing {relpath}; run from the ElyraOps Phase 1 project")
    source = path.read_text(encoding="utf-8")
    for before, after in replacements:
        if before not in source:
            raise SystemExit(f"Cannot safely patch {relpath}: expected code not found or already updated")
        if source.count(before) != 1:
            raise SystemExit(f"Cannot safely patch {relpath}: anchor not unique")
        source = source.replace(before, after, 1)
    prepared[path] = source

for path, content in prepared.items():
    path.write_text(content, encoding="utf-8")
    print("Updated", path.relative_to(root))
print("Gemini support enabled. The project still needs a live key and runtime test.")
