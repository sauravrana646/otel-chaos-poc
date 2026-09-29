import http from 'k6/http';
import { check } from 'k6';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

const BASE = __ENV.JAVA_API_BASE || 'http://127.0.0.1:8080';

export const options = {
  scenarios: {
    spike: {
      executor: 'ramping-arrival-rate',
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 20,
      maxVUs: 120,
      stages: [
        { target: 5, duration: '1m' },
        { target: 25, duration: '1m' },
        { target: 50, duration: '1m' },
        { target: 5, duration: '1m' },
      ],
    },
  },
  thresholds: {
    // Soft during spike; verify recovery separately in poc verify / dashboards.
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  const requestId = `k6-spike-${uuidv4()}`;
  const res = http.post(
    `${BASE}/api/recommendations`,
    JSON.stringify({
      request_id: requestId,
      item_id: 'item-100',
      scenario: 'normal',
    }),
    {
      headers: { 'Content-Type': 'application/json' },
      tags: { name: 'recommendations', scenario: 'spike' },
    },
  );
  check(res, { 'status 200': (r) => r.status === 200 });
}
