"""Explicit, per-tenant, additive SQLite -> PostgreSQL case migration.

No existing PostgreSQL records are overwritten. Default is dry-run.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import os
from pathlib import Path


def main():
    from elyraops import core, pg_cases
    parser=argparse.ArgumentParser()
    parser.add_argument('--organization',required=True,help='Exactly one source tenant to copy')
    parser.add_argument('--apply',action='store_true',help='Write to RLS store; otherwise count only')
    args=parser.parse_args()
    tenant=args.organization
    if not pg_cases.enabled():
        raise SystemExit('ELYRA_CASES_DATABASE_URL must be configured')
    if not 1<=len(tenant)<=100:
        raise SystemExit('Invalid organization')
    source=Path(core.DB_PATH)
    if not source.exists():
        raise SystemExit('SQLite database not found; migration does not create it')
    with sqlite3.connect(str(source)) as db:
        db.row_factory=sqlite3.Row
        cases=[dict(c) for c in db.execute('SELECT * FROM cases WHERE organization=? ORDER BY id',(tenant,))]
        events={c['id']:[dict(e) for e in db.execute('SELECT * FROM events WHERE case_id=? ORDER BY rowid',(c['id'],))] for c in cases}
    print(f'Source tenant: {tenant!r}; SQLite cases: {len(cases)}, events: {sum(map(len,events.values()))}')
    if not args.apply:
        print('Dry-run only. Add --apply after checking the tenant and counts.');return
    from psycopg.types.json import Jsonb
    imported=0
    with pg_cases.connection(tenant) as conn:
        for case in cases:
            exists=conn.execute('SELECT 1 FROM elyra_rls.case_records WHERE id=%s',(case['id'],)).fetchone()
            if exists:
                print('Skipping existing case '+case['id']);continue
            conn.execute("""INSERT INTO elyra_rls.case_records
              (id,tenant_id,title,domain,priority,organization,description,status,created_at,updated_at,
               proposed_action,reasoning,evidence,workflow_run_id)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
              (case['id'],tenant,case['title'],case['domain'],case['priority'],tenant,case['description'],
               case['status'],case['created_at'],case['updated_at'],case['proposed_action'],case['reasoning'],
               Jsonb(json.loads(case['evidence'])),case['workflow_run_id']))
            for event in events[case['id']]:
                conn.execute("""INSERT INTO elyra_rls.case_events
                  (id,case_id,tenant_id,type,message,actor,details,created_at)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                  (event['id'],case['id'],tenant,event['type'],event['message'],event['actor'],
                   Jsonb(json.loads(event['details'])),event['created_at']))
            imported+=1
    print(f'Committed {imported} new cases. SQLite original was not modified.')

if __name__=='__main__':main()
