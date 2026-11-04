"""Phase 3A local bearer-auth, tenant, RBAC, and agent token regression tests."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from elyraops import core, security
from elyraops.server import Handler

TOKENS = {
    'viewer_a': 'a-demo-test-token-viewer-' + 'v'*40,
    'analyst_a': 'a-demo-test-token-analyst-' + 'a'*40,
    'approver_a': 'a-demo-test-token-approver-' + 'p'*40,
    'admin_a': 'a-demo-test-token-admin-' + 'd'*40,
    'analyst_b': 'b-demo-test-token-analyst-' + 'b'*40,
}
AGENT_TOKEN = 'test-internal-service-secret-' + 'i'*42


def test_config():
    roles = {'viewer_a':'viewer', 'analyst_a':'analyst', 'approver_a':'approver', 'admin_a':'admin', 'analyst_b':'analyst'}
    return {
        hashlib.sha256(token.encode()).hexdigest(): {
            'organization': 'Tenant A' if key.endswith('_a') else 'Tenant B',
            'name': 'User ' + key,
            'role': roles[key],
        }
        for key, token in TOKENS.items()
    }


class SecurityPolicyTests(unittest.TestCase):
    def test_security_mode_fails_closed_without_credentials(self):
        with patch.dict(os.environ, {'ELYRA_SECURITY_MODE':'required','ELYRA_ACCESS_TOKENS_JSON':''}):
            with self.assertRaises(security.SecurityError) as exc:
                security.authenticate('Bearer ' + TOKENS['viewer_a'])
        self.assertEqual(exc.exception.status, 503)

    def test_token_not_accepted_with_other_digest(self):
        with patch.dict(os.environ, {'ELYRA_SECURITY_MODE':'required','ELYRA_ACCESS_TOKENS_JSON':json.dumps(test_config())}):
            self.assertEqual(security.authenticate('Bearer '+TOKENS['viewer_a']).role, 'viewer')
            with self.assertRaises(security.SecurityError) as exc:
                security.authenticate('Bearer '+TOKENS['viewer_a']+'x')
            self.assertEqual(exc.exception.status, 401)

    def test_role_scope_and_internal_secret(self):
        with patch.dict(os.environ, {'ELYRA_SECURITY_MODE':'required','ELYRA_ACCESS_TOKENS_JSON':json.dumps(test_config()),'ELYRA_AGENT_TOKEN':AGENT_TOKEN}):
            p=security.authenticate('Bearer '+TOKENS['analyst_a'])
            security.authorize(p,'investigate','Tenant A')
            with self.assertRaises(security.SecurityError) as wrong_org:
                security.authorize(p,'read','Tenant B')
            self.assertEqual(wrong_org.exception.status,404)
            with self.assertRaises(security.SecurityError) as wrong_role:
                security.authorize(p,'decide','Tenant A')
            self.assertEqual(wrong_role.exception.status,403)
            self.assertTrue(security.internal_token_valid(AGENT_TOKEN))
            self.assertFalse(security.internal_token_valid('bad'))


class GuardedHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=4)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_db = core.DB_PATH
        core.DB_PATH = os.path.join(self.temp.name, 'guarded.db')
        core.initialize()
        self.env = patch.dict(os.environ, {
            'ELYRA_SECURITY_MODE': 'required',
            'ELYRA_ACCESS_TOKENS_JSON': json.dumps(test_config()),
            'ELYRA_AGENT_TOKEN': AGENT_TOKEN,
            'ELYRA_AGENT_URL': '',
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        core.DB_PATH = self.previous_db
        self.temp.cleanup()

    def request(self, method, path, role=None, body=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=8)
        headers = {}
        if role:
            headers['Authorization'] = 'Bearer ' + TOKENS[role]
        if body is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(body)
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        result = resp.status, json.loads(resp.read())
        conn.close()
        return result

    def sample(self, organization='Tenant B'):
        return {'title':'Duplicate invoice charge',
                'description':'Two transactions were processed for the exact same service invoice.',
                'domain':'Billing', 'priority':'High', 'organization':organization}

    def test_unauthenticated_requests_are_rejected(self):
        status, _ = self.request('GET', '/api/cases')
        self.assertEqual(status, 401)
        status, _ = self.request('POST','/api/cases',body=self.sample())
        self.assertEqual(status, 401)
        status, config = self.request('GET','/api/auth/config')
        self.assertEqual((status,config['enabled']),(200,True))

    def test_org_spoofing_and_cross_tenant_read_blocked(self):
        status, created = self.request('POST','/api/cases','analyst_a',self.sample('Tenant B'))
        self.assertEqual(status,201)
        case_id = created['id']
        self.assertEqual(core.get_case(case_id)['organization'],'Tenant A')
        status, _ = self.request('GET', '/api/cases/'+case_id, 'analyst_b')
        self.assertEqual(status,404)
        status, own = self.request('GET', '/api/cases', 'analyst_a')
        self.assertEqual(status,200)
        self.assertEqual([x['id'] for x in own['items']],[case_id])
        status, others = self.request('GET', '/api/cases', 'analyst_b')
        self.assertEqual(status,200)
        self.assertEqual(others['items'], [])
        status, summary = self.request('GET','/api/dashboard','analyst_a')
        self.assertEqual((status,summary['cases_total']), (200,1))

    def test_role_permissions_and_actor_override(self):
        status, created = self.request('POST','/api/cases','analyst_a',self.sample())
        self.assertEqual(status,201)
        case_id=created['id']
        status, _ = self.request('POST','/api/cases','viewer_a',self.sample())
        self.assertEqual(status,403)
        status, _ = self.request('POST',f'/api/cases/{case_id}/investigate','viewer_a',{})
        self.assertEqual(status,403)
        status, _ = self.request('POST',f'/api/cases/{case_id}/investigate','analyst_b',{})
        self.assertEqual(status,404)
        status, _ = self.request('POST',f'/api/cases/{case_id}/investigate','analyst_a',{})
        self.assertEqual(status,200)
        status, _ = self.request('POST',f'/api/cases/{case_id}/decision','analyst_a',{'decision':'approve','actor':'Spoofed'})
        self.assertEqual(status,403)
        status, _ = self.request('POST',f'/api/cases/{case_id}/decision','approver_a',{'decision':'approve','actor':'Spoofed'})
        self.assertEqual(status,200)
        events=core.get_case(case_id)['events']
        approved = [x for x in events if x['type']=='approved']
        self.assertEqual(len(approved),1)
        self.assertEqual(approved[0]['actor'],'User approver_a')

    def test_cross_tenant_decision_cannot_update(self):
        status, created = self.request('POST','/api/cases','analyst_b',self.sample())
        case_id = created['id']
        self.assertEqual(status,201)
        core.investigate(case_id)
        status, _ = self.request('POST',f'/api/cases/{case_id}/decision','approver_a',{'decision':'approve','actor':'X'})
        self.assertEqual(status,404)
        self.assertEqual(core.get_case(case_id)['status'],'Pending approval')


class AgentAuthTests(unittest.TestCase):
    @unittest.skipUnless(__import__('importlib').util.find_spec('fastapi') and __import__('importlib').util.find_spec('httpx'), 'FastAPI TestClient optional')
    def test_internal_service_rejects_missing_and_cross_organization(self):
        from fastapi.testclient import TestClient
        from agent_service.app import app
        with tempfile.TemporaryDirectory() as tmp:
            before = core.DB_PATH
            core.DB_PATH = os.path.join(tmp,'agent.db')
            try:
                core.initialize()
                with patch.dict(os.environ, {'ELYRA_SECURITY_MODE':'required','ELYRA_AGENT_TOKEN':AGENT_TOKEN}):
                    client=TestClient(app)
                    no_token=client.post('/v1/investigate',json={'case_id':'EC-1042','organization':'Northstar Commerce'})
                    self.assertEqual(no_token.status_code,401)
                    wrong_scope=client.post('/v1/investigate',headers={'X-Agent-Token':AGENT_TOKEN},json={'case_id':'EC-1042','organization':'Wrong Tenant'})
                    self.assertEqual(wrong_scope.status_code,404)
                    self.assertEqual(core.get_case('EC-1042')['status'],'Open')
            finally:
                core.DB_PATH = before


if __name__ == '__main__':
    unittest.main()
