"""Apply Phase 5 payload only to known, verified ElyraOps main-branch sources.

Run at the project root: python scripts/apply_observability_phase5.py
Works offline and refuses to overwrite arbitrary user changes.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / "phase5_payload"

# Git blob SHA1 of the verified Phase 4 main branch (fc4eb0e).
EXPECTED = {
    "agent_service/app.py": "347fc55d746c680c22747dc5b95a146adbc4f2a2",
    "agent_service/workflow.py": "4faafa179d15d57521e3c80e82c8b86e7691bb2b",
    "elyraops/server.py": "0033f280cdb1374cf764572cbd66d2e04ed4d7e5",
    "elyraops/agent_client.py": "6c8256e16b9d20f6a86ee85b2ed67b4b71fec55d",
}


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def main():
    if not PAYLOAD.is_dir():
        raise SystemExit("Phase 5 payload missing. Extract the ZIP into the repository first.")
    required = [ROOT / name for name in EXPECTED]
    staged = [PAYLOAD / name for name in EXPECTED]
    for current, new, old_hash in zip(required, staged, EXPECTED.values()):
        if not current.is_file() or not new.is_file():
            raise SystemExit(f"Missing expected file: {current.relative_to(ROOT)} or payload")
        current_hash, new_hash = blob_sha(current.read_bytes()), blob_sha(new.read_bytes())
        if current_hash not in {old_hash, new_hash}:
            raise SystemExit(f"Refusing to overwrite customized file: {current.relative_to(ROOT)}")
    for current, new in zip(required, staged):
        if current.read_bytes() != new.read_bytes():
            shutil.copyfile(new, current)
            print("Updated", current.relative_to(ROOT))
        else:
            print("Already updated", current.relative_to(ROOT))
    shutil.rmtree(PAYLOAD)
    print("Phase 5 installed. No database migration required.")
    print("Run: python -m unittest discover -s tests -v")


if __name__ == "__main__":
    main()
