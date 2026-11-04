"""Phase 3B offline guard tests plus optional live PostgreSQL RLS integration."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from elyraops import core, pg_cases


class Phase3BOfflineTests(unittest.TestCase):
    def test_postgres_case_mode_is_opt_in(self):
        with patch.dict(os.environ, {'ELYRA_CASES_DATABASE_URL':''}):
            self.assertFalse(pg_cases.enabled())

    def test_cannot_enable_postgres_without_guarded_auth(self):
        with patch.dict(os.environ, {'ELYRA_CASES_DATABASE_URL':'postgresql://example.invalid/db',
                                     'ELYRA_SECURITY_MODE':'disabled'}):
            with self.assertRaises(pg_cases.CaseStoreUnavailable):
                pg_cases.list_cases('Tenant A')

    def test_pg_requests_require_trusted_organization(self):
        with patch.dict(os.environ, {'ELYRA_SECURITY_MODE':'required',
                                     'ELYRA_CASES_DATABASE_URL':'postgresql://example.invalid/db'}):
            with self.assertRaises(pg_cases.CaseStoreUnavailable):
                pg_cases.get_case('EC-ANY', None)

    def test_core_pg_dispatch_never_falls_back_to_sqlite(self):
        with patch.dict(os.environ, {'ELYRA_SECURITY_MODE':'required',
                                     'ELYRA_CASES_DATABASE_URL':'postgresql://example.invalid/db'}):
            with patch.object(pg_cases,'get_case',side_effect=pg_cases.CaseStoreUnavailable('DB down')) as call:
                with self.assertRaises(pg_cases.CaseStoreUnavailable):
                    core.get_case('EC-1042','Tenant A')
                call.assert_called_once_with('EC-1042','Tenant A')

    def test_postgres_migration_has_explicit_apply_gate(self):
        from pathlib import Path
        content=(Path(__file__).resolve().parents[1]/'scripts'/'migrate_sqlite_cases.py').read_text()
        self.assertIn("parser.add_argument('--apply',action='store_true'",content)


@unittest.skipUnless(os.environ.get('ELYRA_RLS_LIVE_TEST') == '1',
                     'Set ELYRA_RLS_LIVE_TEST=1 and ELYRA_CASES_DATABASE_URL for live RLS test')
class Phase3BLiveTests(unittest.TestCase):
    def test_rls_blocks_cross_tenant_unscoped_select_and_write(self):
        import uuid
        import psycopg
        a='Test RLS A '+uuid.uuid4().hex[:8]
        b='Test RLS B '+uuid.uuid4().hex[:8]
        env=patch.dict(os.environ,{'ELYRA_SECURITY_MODE':'required'})
        env.start()
        case_id=None
        try:
            pg_cases.verify_backend()
            created=pg_cases.create_case({'title':'Synthetic billing case',
                'description':'Testing tenant isolation safely with fake payment data.',
                'domain':'Billing','priority':'High'},a)
            case_id=created['id']
            self.assertIsNotNone(pg_cases.get_case(case_id,a))
            self.assertIsNone(pg_cases.get_case(case_id,b))
            with pg_cases.connection(b) as conn:
                self.assertEqual(conn.execute('SELECT id FROM elyra_rls.case_records WHERE id=%s',(case_id,)).fetchall(),[])
                self.assertEqual(conn.execute('SELECT id FROM elyra_rls.case_events WHERE case_id=%s',(case_id,)).fetchall(),[])
            with self.assertRaises(pg_cases.CaseStoreUnavailable):
                with pg_cases.connection(a) as conn:
                    conn.execute('UPDATE elyra_rls.case_records SET tenant_id=%s,organization=%s WHERE id=%s',(b,b,case_id))
            with psycopg.connect(os.environ['ELYRA_CASES_DATABASE_URL']) as conn:
                self.assertEqual(conn.execute('SELECT id FROM elyra_rls.case_records WHERE id=%s',(case_id,)).fetchall(),[])
            with pg_cases.connection(a) as conn:
                self.assertEqual(conn.execute('SELECT current_setting(%s, true) AS tenant',('elyra.tenant_id',)).fetchone()['tenant'],a)
        finally:
            env.stop()
            admin=os.environ.get('ELYRA_RLS_ADMIN_DATABASE_URL','').strip()
            if case_id and admin:
                # Cleanup is optional, exact-id scoped and uses local setup admin only.
                with psycopg.connect(admin) as conn:
                    conn.execute('DELETE FROM elyra_rls.case_events WHERE case_id=%s',(case_id,))
                    conn.execute('DELETE FROM elyra_rls.case_records WHERE id=%s',(case_id,))

if __name__=='__main__': unittest.main()
