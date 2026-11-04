// Phase 6 local Docker read-only benchmark; never generate cases or approvals.
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '15s',
  thresholds: {
    'http_req_failed': ['rate<0.01'],
    'http_req_duration': ['p(95)<1000'],
  },
};

const base = __ENV.ELYRA_K6_BASE_URL || 'http://127.0.0.1:18082';
if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base)) {
  throw new Error('Benchmark only localhost instances of the demo');
}
export default function () {
  const health = http.get(`${base}/health`);
  check(health, { 'dashboard liveness': (r) => r.status === 200 });
  const config = http.get(`${base}/api/auth/config`);
  check(config, { 'auth config reachable': (r) => r.status === 200 });
  sleep(0.5);
}
