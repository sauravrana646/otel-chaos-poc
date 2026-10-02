import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';

const BASE = __ENV.JAVA_API_BASE || 'http://127.0.0.1:8080';
const RPS = Number(__ENV.POC_RPS || '1');
const DURATION = __ENV.POC_DURATION || '1m';
const MAX_P95_MS = Number(__ENV.POC_MAX_P95_MS || '30000');
const PROVIDER = __ENV.POC_PROVIDER || 'mock';

export const options = {
  scenarios: {
    constant: {
      executor: 'constant-arrival-rate',
      rate: RPS,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: Math.max(10, RPS * 10),
      maxVUs: Math.max(50, RPS * 30),
    },
  },
  thresholds: {
    checks: ['rate>0.95'],
    http_req_failed: ['rate<0.05'],
    http_req_duration: [`p(95)<${MAX_P95_MS}`],
    dropped_iterations: ['count==0'],
  },
};

export default function () {
  const requestId = `k6-constant-${RPS}rps-${Date.now()}-${exec.vu.idInTest}-${exec.scenario.iterationInTest}`;
  const res = http.post(
    `${BASE}/api/recommendations`,
    JSON.stringify({ request_id: requestId, item_id: 'item-100', scenario: 'normal', provider: PROVIDER }),
    {
      headers: { 'Content-Type': 'application/json' },
      tags: { name: 'recommendations', scenario: `constant-${RPS}rps` },
    },
  );
  check(res, {
    'status 200': (r) => r.status === 200,
    'request_id matches': (r) => {
      try {
        return JSON.parse(r.body).request_id === requestId;
      } catch (_) {
        return false;
      }
    },
  });
}
