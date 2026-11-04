// Phase 7: small, bounded, READ-ONLY localhost HTTP smoke benchmark.
// Does NOT measure RAG, LangGraph, Gemini, SQL case reads, writes or approvals.
import http from 'k6/http';
import { check, sleep } from 'k6';

const base = __ENV.ELYRA_K6_BASE_URL || 'http://127.0.0.1:18082';
if (!/^http:\/\/(127\.0\.0\.1|localhost):18082$/.test(base)) {
  throw new Error('Portfolio benchmark must target localhost:18082 only');
}
const vus = Number(__ENV.ELYRA_K6_VUS || '5');
const duration = __ENV.ELYRA_K6_DURATION || '20s';
const match = /^(\d+)s$/.exec(duration);
if (!Number.isInteger(vus) || vus < 1 || vus > 20 || !match || Number(match[1]) < 5 || Number(match[1]) > 120) {
  throw new Error('Bounded benchmark: 1–20 virtual users; 5s–120s duration');
}

export const options = {
  vus,
  duration,
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1000'],
  },
  tags: { workload: 'read_only_dashboard_smoke' },
};

export default function () {
  const health = http.get(`${base}/health`, { tags: { endpoint: 'health' } });
  check(health, { 'dashboard GET /health returns 200': (r) => r.status === 200 });
  const auth = http.get(`${base}/api/auth/config`, { tags: { endpoint: 'auth_config' } });
  check(auth, { 'dashboard GET /api/auth/config returns 200': (r) => r.status === 200 });
  sleep(0.35);
}
