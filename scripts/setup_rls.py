"""Create local dedicated RLS runtime role and schema. No secrets in Git."""
from __future__ import annotations

import os
import secrets
import shlex
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit


def main():
    import psycopg
    from psycopg import sql
    admin = os.environ.get('ELYRA_RLS_ADMIN_DATABASE_URL','').strip()
    if not admin:
        raise SystemExit('Set ELYRA_RLS_ADMIN_DATABASE_URL to the local PostgreSQL owner URL first')
    env_path=Path('.env.rls')
    if env_path.exists():
        raise SystemExit('.env.rls exists: setup already ran. Nothing changed.')
    password=secrets.token_urlsafe(36)
    parsed=urlsplit(admin)
    if parsed.scheme not in {'postgresql','postgres'} or not parsed.hostname or not parsed.path:
        raise SystemExit('Expected a postgresql:// connection URL')
    if parsed.port is None:
        netloc=f'elyra_cases_runtime:{quote(password,safe="")}@{parsed.hostname}'
    else:
        netloc=f'elyra_cases_runtime:{quote(password,safe="")}@{parsed.hostname}:{parsed.port}'
    runtime=urlunsplit((parsed.scheme,netloc,parsed.path,parsed.query,parsed.fragment))
    sql_script=Path(__file__).resolve().parent.parent/'sql'/'phase3b_rls.sql'
    with psycopg.connect(admin,connect_timeout=6) as conn:
        with conn.transaction():
            exists=conn.execute("SELECT 1 FROM pg_roles WHERE rolname='elyra_cases_runtime'").fetchone()
            if exists:
                raise SystemExit('elyra_cases_runtime already exists. Refusing to rotate it implicitly.')
            conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT').format(
                sql.Identifier('elyra_cases_runtime'),sql.Literal(password)))
            conn.execute(sql_script.read_text())
    env_path.write_text('export ELYRA_CASES_DATABASE_URL='+shlex.quote(runtime)+'\n')
    env_path.chmod(0o600)
    print('Created RLS schema, dedicated app role, and .env.rls (0600). No secret displayed.')
    print('Start only with ELYRA_SECURITY_MODE=required and use the non-owner runtime URL.')


if __name__=='__main__':
    main()
