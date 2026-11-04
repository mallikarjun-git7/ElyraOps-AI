// Read-only local smoke test. Never load-test POST /v1/investigate: it mutates state.
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

const base = __ENV.ELYRA_K6_BASE_URL || 'http://127.0.0.1:8091';
if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base)) {
  throw new Error('This demonstration runs against a localhost target only');
}

export default function () {
  const health = http.get(`${base}/health`);
  check(health, { 'liveness returns 200': (r) => r.status === 200 });
  const ready = http.get(`${base}/ready`);
  check(ready, { 'readiness returns 200': (r) => r.status === 200 });
  sleep(0.5);
}
