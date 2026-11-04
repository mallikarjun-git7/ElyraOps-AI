"""Explicit local-only administrator migration for public.rag_chunks RLS."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Enable PostgreSQL RLS for demo RAG documents")
    parser.add_argument("--apply", action="store_true", help="Apply the reviewed RLS migration")
    args = parser.parse_args()
    if not args.apply:
        print("Dry run: setup will preserve rag_chunks data, add FORCE RLS and grant SELECT to the non-owner case runtime role.")
        print("Review sql/phase4_secure_rag.sql, then repeat with --apply.")
        return
    url = os.environ.get("ELYRA_RLS_ADMIN_DATABASE_URL", "").strip()
    if not url:
        parser.error("Set ELYRA_RLS_ADMIN_DATABASE_URL to the trusted local PostgreSQL owner URL")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Install requirements-rag.txt first") from exc
    sql_script = Path(__file__).resolve().parents[1] / "sql" / "phase4_secure_rag.sql"
    # Explicitly local, not an HTTP endpoint; no secret is logged.
    from urllib.parse import urlsplit
    host = urlsplit(url).hostname
    if host not in {"127.0.0.1", "localhost"}:
        parser.error("Only localhost PostgreSQL administration is supported")
    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            owner = conn.execute("SELECT current_user").fetchone()[0]
            relation = conn.execute("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='public.rag_chunks'::regclass").fetchone()[0]
            if owner != relation:
                parser.error("Use the actual rag_chunks table owner for this local migration")
            conn.execute(sql_script.read_text(encoding="utf-8"))
    except psycopg.Error as exc:
        raise SystemExit("Secure RAG migration failed. Check local DB role, schema and permissions.") from exc
    print("Secure RAG RLS enabled on public.rag_chunks; existing embeddings preserved. No secrets displayed.")


if __name__ == "__main__":
    main()
