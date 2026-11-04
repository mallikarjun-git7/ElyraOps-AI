"""Safe local installation of Phase 4 secure-RAG patch on the Phase 3B main commit."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

RAG_BASE_SHA = '9ca6ff2679151d4a5362280a06229a5dfedc04ff07049ae852314164d7050599'
CI_BASE_SHA = '65d89ba4f6dcf5b4fe74e7cd58c4bc2ef4df027614362dca266a83519d581d7d'


def digest(text: bytes) -> str:
    return hashlib.sha256(text).hexdigest()


def main():
    repo = Path(__file__).resolve().parents[1]
    payload = repo / 'phase4_payload'
    pairs = (
        (repo / 'agent_service' / 'rag_pg.py', payload / 'rag_pg.py', RAG_BASE_SHA),
        (repo / '.github' / 'workflows' / 'ci.yml', payload / 'ci.yml', CI_BASE_SHA),
    )
    # Validate ALL inputs before writing any output; never overwrite an
    # unknown local modification or discard a user's unrelated changes.
    for dest, src, expected in pairs:
        if not dest.is_file() or not src.is_file():
            raise SystemExit('Required patch files missing: check ZIP extraction at the repository root')
        current = digest(dest.read_bytes())
        updated = digest(src.read_bytes())
        if current not in {expected, updated}:
            raise SystemExit(f'Unexpected local changes in {dest.relative_to(repo)}. Patch not applied; review git diff first.')
    for dest, src, _ in pairs:
        if digest(dest.read_bytes()) != digest(src.read_bytes()):
            dest.write_bytes(src.read_bytes())
            print('Updated:', dest.relative_to(repo))
        else:
            print('Already current:', dest.relative_to(repo))
    # ZIP payload is installation-only and must never be accidentally committed.
    shutil.rmtree(payload)
    print('Secure RAG Phase 4 source patch applied; review SECURE_RAG_PHASE4.md and run tests.')


if __name__ == '__main__':
    main()
