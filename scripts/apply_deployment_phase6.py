"""Apply the Phase 6 patch after extracting its ZIP at the repository root.
Refuses to overwrite unrelated local edits to the Phase 5 main-branch files.
No network operations, DB mutations, provider requests or secret reads.
"""
from __future__ import annotations
import hashlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / 'phase6_payload'
EXPECTED = {'elyraops/server.py': '3578d59b45500620ff37b47fcc5b90671bd06bab', 'elyraops/agent_client.py': 'df6dd987356d90fb393741542e29e9a31b6ceed8', '.dockerignore': 'e45ed0450f81db1bf9601932b925a91fdc781443', 'docker-compose.yml': '8be846509ebc9a8cd5d20a6241cff81082088316', '.github/workflows/ci.yml': '9517ec177c7da22ed40adb20b8f5e81d4c55b9a5', 'tests/test_observability_phase5.py': 'b1e4d95a67fe154589bc368b22cc41dc5e96b9a3'}


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def main():
    for relative, original in EXPECTED.items():
        current, replacement = ROOT / relative, PAYLOAD / relative
        if not current.is_file() or not replacement.is_file():
            raise SystemExit("Missing expected base or Phase 6 payload file: " + relative)
        actual, patch_sha = git_blob(current.read_bytes()), git_blob(replacement.read_bytes())
        if actual not in {original, patch_sha}:
            raise SystemExit("Refusing to overwrite local modifications to: " + relative)
    for relative in EXPECTED:
        current, replacement = ROOT / relative, PAYLOAD / relative
        if current.read_bytes() != replacement.read_bytes():
            shutil.copyfile(replacement, current)
            print('Updated', relative)
        else:
            print('Already updated', relative)
    shutil.rmtree(PAYLOAD)
    print('Phase 6 files applied. No database migration or credential changes were made.')
    print('Run the offline tests in DEPLOYMENT_PHASE6.md before Docker startup.')

if __name__ == '__main__': main()
