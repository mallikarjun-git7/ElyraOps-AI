"""Install Phase 7 recruiter-facing docs and read-only benchmark tools safely.

Requires a clean, expected Phase 6 README; refuses to overwrite user files.
No external requests, passwords, database migrations, or application changes.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / 'phase7_payload'
EXPECTED_README_GIT_SHA = '5f4c350e008fe1ed3858af540c5819d2e4127bf3'
FILE_PATHS = (
    'README.md',
    'docs/portfolio/ARCHITECTURE.md',
    'docs/portfolio/DEMO.md',
    'docs/portfolio/SCREENSHOTS.md',
    'docs/portfolio/BENCHMARKS.md',
    'docs/portfolio/LIMITATIONS.md',
    'load/k6_portfolio.js',
    'scripts/phase7_benchmark_report.py',
    'tests/test_portfolio_phase7.py',
)


def git(*args: str) -> str:
    return subprocess.check_output(('git', *args), cwd=ROOT, text=True).strip()


def install() -> None:
    if git('branch', '--show-current') != 'feat/portfolio-benchmarks':
        raise RuntimeError('Switch to feat/portfolio-benchmarks before installing Phase 7')
    if git('status', '--porcelain', '--', 'README.md'):
        raise RuntimeError('README.md contains uncommitted changes; refusing to replace it')
    if git('hash-object', 'README.md') != EXPECTED_README_GIT_SHA:
        raise RuntimeError('README.md does not match the reviewed Phase 6 version; no changes applied')
    for rel in FILE_PATHS:
        src = PAYLOAD / rel
        dst = ROOT / rel
        if not src.is_file():
            raise RuntimeError(f'Missing upgrade payload: {rel}')
        if rel != 'README.md' and dst.exists():
            raise RuntimeError(f'Would overwrite an existing file: {rel}')
    for rel in FILE_PATHS:
        src = PAYLOAD / rel
        dst = ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    shutil.rmtree(PAYLOAD)
    print('Phase 7 installed: README refresh, architecture/demo/limitations docs,')
    print('safe read-only k6 workload, measured-report generator, regression tests.')
    print('No private config, database data, container state or API keys were touched.')


if __name__ == '__main__':
    install()
