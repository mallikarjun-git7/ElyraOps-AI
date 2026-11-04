"""Optional PostgreSQL-backed case/event store with enforced per-transaction RLS.

Local demonstration only. Authenticated HTTP principals must supply the tenant;
never derive it from the client request body. The runtime role must NOT be a
superuser, table owner, or have BYPASSRLS. Never accept arbitrary SQL here.
"""
from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager

RUNTIME_ROLE = 'elyra_cases_runtime'
SCHEMA = 'elyra_rls'


class CaseStoreUnavailable(RuntimeError):
    """The optional PostgreSQL case backend cannot be used safely."""


def enabled():
    return bool(os.environ.get('ELYRA_CASES_DATABASE_URL', '').strip())


def _psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise CaseStoreUnavailable('Install requirements-rag.txt for PostgreSQL case store') from exc
    return psycopg, dict_row, Jsonb


def _tenant(organization):
    from . import security
    if not security.enabled():
        raise CaseStoreUnavailable('PostgreSQL case mode requires ELYRA_SECURITY_MODE=required')
    if not isinstance(organization, str) or not 1 <= len(organization) <= 100:
        raise CaseStoreUnavailable('An authenticated organization is required for PostgreSQL case operations')
    return organization


@contextmanager
def connection(organization):
    """One dedicated transaction. SET LOCAL never leaks to subsequent requests."""
    organization = _tenant(organization)
    psycopg, dict_row, _ = _psycopg()
    url = os.environ.get('ELYRA_CASES_DATABASE_URL', '').strip()
    if not url:
        raise CaseStoreUnavailable('ELYRA_CASES_DATABASE_URL is missing')
    try:
        with psycopg.connect(url, row_factory=dict_row, connect_timeout=5) as conn:
            actual = conn.execute('SELECT current_user AS name').fetchone()['name']
            if actual != RUNTIME_ROLE:
                raise CaseStoreUnavailable('Runtime must connect as the dedicated non-owner RLS role')
            conn.execute('SELECT set_config(%s, %s, true)', ('elyra.tenant_id', organization))
            yield conn
    except psycopg.Error as exc:
        raise CaseStoreUnavailable('PostgreSQL case transaction failed') from exc


def verify_backend():
    """Fail startup if the role, schema or forced policies are missing."""
    _tenant('startup-probe')
    with connection('startup-probe') as conn:
        role = conn.execute('SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
        if not role or role['rolsuper'] or role['rolbypassrls']:
            raise CaseStoreUnavailable('Runtime database role has unsafe privileges')
        rels = conn.execute("""
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
              FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='elyra_rls' AND c.relname IN ('case_records','case_events')
        """).fetchall()
        if len(rels) != 2 or not all(x['relrowsecurity'] and x['relforcerowsecurity'] for x in rels):
            raise CaseStoreUnavailable('Case tables must have ENABLE and FORCE ROW LEVEL SECURITY')
        policies = conn.execute("""
            SELECT tablename FROM pg_policies WHERE schemaname='elyra_rls'
              AND tablename IN ('case_records','case_events')
              AND policyname='tenant_access'
        """).fetchall()
        if len(policies) != 2:
            raise CaseStoreUnavailable('Tenant RLS policies are missing')


def _event(conn, case_id, tenant, typ, message, actor='system', details=None):
    _, _, Jsonb = _psycopg()
    from . import core
    conn.execute("""INSERT INTO elyra_rls.case_events
      (id,case_id,tenant_id,type,message,actor,details,created_at)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
      (str(uuid.uuid4()),case_id,tenant,typ,message,actor,Jsonb(details or {}),core.now()))


def list_cases(organization):
    with connection(organization) as conn:
        return conn.execute("""SELECT id,title,domain,priority,organization,description,status,created_at,updated_at
              FROM elyra_rls.case_records ORDER BY id""").fetchall()


def get_case(case_id, organization):
    with connection(organization) as conn:
        row = conn.execute('SELECT * FROM elyra_rls.case_records WHERE id=%s', (case_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result['evidence'] = result['evidence'] if isinstance(result['evidence'], list) else json.loads(result['evidence'])
        events = conn.execute("""SELECT id,case_id,type,message,actor,details,created_at
            FROM elyra_rls.case_events WHERE case_id=%s ORDER BY inserted_at DESC,id DESC LIMIT 30""", (case_id,)).fetchall()
        result['events'] = [dict(x) for x in events]
        return result


def create_case(payload, organization):
    from . import core
    tenant = _tenant(organization)
    case_id = 'EC-' + uuid.uuid4().hex[:14].upper()
    stamp = core.now()
    with connection(tenant) as conn:
        conn.execute("""INSERT INTO elyra_rls.case_records
        (id,tenant_id,title,domain,priority,organization,description,status,created_at,updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'Open',%s,%s)""",
        (case_id,tenant,payload['title'],payload['domain'],payload['priority'],tenant,payload['description'],stamp,stamp))
        _event(conn,case_id,tenant,'created','New case created', 'demo-operator')
    return {'id':case_id,'status':'Open'}


def investigate(case_id, organization):
    """Deterministic non-LLM path; retrieval policy text remains in local SQLite."""
    from . import core
    tenant = _tenant(organization)
    with connection(tenant) as conn:
        row = conn.execute('SELECT * FROM elyra_rls.case_records WHERE id=%s FOR UPDATE',(case_id,)).fetchone()
        if row is None:
            raise KeyError(case_id)
        if row['status'] != 'Open':
            return {'case_id':case_id,'status':row['status'],'workflow_run_id':row['workflow_run_id'],'already_processed':True}
        with core.connect() as sqlite_db:
            evidence = core.retrieve(sqlite_db,row['title']+' '+row['description'],row['domain'])
        action,policy=core.ACTIONS.get(row['domain'],('Escalate case for review','Human review is required.'))
        run_id=str(uuid.uuid4())
        _,_,Jsonb=_psycopg()
        conn.execute("""UPDATE elyra_rls.case_records
            SET status='Pending approval', proposed_action=%s, reasoning=%s,
            evidence=%s,workflow_run_id=%s,updated_at=%s WHERE id=%s""",
            (action,policy+' Recommended action: '+action,Jsonb(evidence),run_id,core.now(),case_id))
        for typ,description in [
            ('triage_agent',f'Classified case as {row["domain"]}; priority: {row["priority"]}'),
            ('retrieval_agent',f'Found {len(evidence)} supporting policy documents'),
            ('resolution_agent','Prepared recommendation; execution blocked pending approval')]:
            _event(conn,case_id,tenant,typ,description,typ,{'run_id':run_id})
        _event(conn,case_id,tenant,'approval_requested','Human authorization required before any execution','workflow-engine',{'action':action})
    return {'case_id':case_id,'status':'Pending approval','workflow_run_id':run_id,'already_processed':False}


def commit_graph_result(case_id, organization, result):
    """Atomic result after LangGraph has run outside a DB transaction."""
    from . import core
    tenant=_tenant(organization)
    run_id=str(uuid.uuid4())
    _,_,Jsonb=_psycopg()
    with connection(tenant) as conn:
        row=conn.execute('SELECT status,workflow_run_id FROM elyra_rls.case_records WHERE id=%s FOR UPDATE',(case_id,)).fetchone()
        if row is None:
            raise KeyError(case_id)
        if row['status'] != 'Open':
            return {'case_id':case_id,'status':row['status'],'workflow_run_id':row['workflow_run_id'],'already_processed':True}
        conn.execute("""UPDATE elyra_rls.case_records SET status='Pending approval',
            proposed_action=%s,reasoning=%s,evidence=%s,workflow_run_id=%s,updated_at=%s
            WHERE id=%s""",(result['action'],result['reasoning'],Jsonb(result['evidence']),run_id,core.now(),case_id))
        for stage,message in [
            ('triage_agent',f'LangGraph triage: {result["domain"]} | {result["priority"]}'),
            ('retrieval_agent',f'LangGraph retrieved {len(result["evidence"])} policy references'),
            ('resolution_agent',f'Proposed a bounded recommendation ({result["mode"]}); requires human approval')]:
            _event(conn,case_id,tenant,stage,message,'langgraph',{'run_id':run_id,'mode':result['mode']})
        _event(conn,case_id,tenant,'approval_requested','Explicit human approval required; no external action taken','langgraph',{'action':result['action']})
    return {'case_id':case_id,'status':'Pending approval','workflow_run_id':run_id,'already_processed':False,'mode':result['mode']}


def decide(case_id,decision,actor,organization):
    from . import core
    tenant=_tenant(organization)
    with connection(tenant) as conn:
        row=conn.execute('SELECT status,proposed_action FROM elyra_rls.case_records WHERE id=%s FOR UPDATE',(case_id,)).fetchone()
        if row is None:
            raise KeyError(case_id)
        if row['status'] != 'Pending approval':
            raise ValueError('Case must be pending approval')
        if decision=='approve':
            status='Approved · simulated'
            _event(conn,case_id,tenant,'approved','Action approved by demo operator',actor)
            _event(conn,case_id,tenant,'simulated_execution','SIMULATION ONLY: no external system changed', 'execution-adapter',{'action':row['proposed_action']})
        else:
            status='Rejected'
            _event(conn,case_id,tenant,'rejected','Proposed action rejected by demo operator',actor)
        conn.execute('UPDATE elyra_rls.case_records SET status=%s,updated_at=%s WHERE id=%s', (status,core.now(),case_id))
    return {'case_id':case_id,'status':status}
