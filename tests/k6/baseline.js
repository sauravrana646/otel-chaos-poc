import http from 'k6/http';
import { check, sleep } from 'k6';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// Target via kubectl port-forward or OrbStack service URL.
const BASE = __ENV.JAVA_API_BASE || 'http://127.0.0.1:8080';

export const options = {
  scenarios: {
    baseline: {
      executor: 'constant-arrival-rate',
      rate: 5,
      timeUnit: '1s',
      duration: '2m',
      preAllocatedVUs: 10,
      maxVUs: 50,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1000'],
    dropped_iterations: ['count==0'],
  },
};

export default function () {
  const requestId = `k6-${uuidv4()}`;
  const payload = JSON.stringify({
    request_id: requestId,
    item_id: 'item-100',
    scenario: 'normal',
  });
  const res = http.post(`${BASE}/api/recommendations`, payload, {
    headers: { 'Content-Type': 'application/json' },
    tags: { name: 'recommendations', scenario: 'baseline' },
  });
  check(res, {
    'status 200': (r) => r.status === 200,
    'has request_id': (r) => {
      try {
        return JSON.parse(r.body).request_id === requestId;
      } catch (_) {
        return false;
      }
    },
  });
  sleep(0.01);
}
