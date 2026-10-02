import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';

const BASE = __ENV.JAVA_API_BASE || 'http://127.0.0.1:8080';
const PROVIDER = __ENV.POC_PROVIDER || 'mock';

export const options = {
  scenarios: {
    warmup: {
      executor: 'constant-arrival-rate',
      exec: 'warmup',
      rate: 5,
      timeUnit: '1s',
      duration: '1m',
      preAllocatedVUs: 10,
      maxVUs: 30,
    },
    spike: {
      executor: 'constant-arrival-rate',
      exec: 'spike',
      startTime: '1m',
      rate: 50,
      timeUnit: '1s',
      duration: '1m',
      preAllocatedVUs: 50,
      maxVUs: 120,
    },
    recovery: {
      executor: 'constant-arrival-rate',
      exec: 'recovery',
      startTime: '2m',
      rate: 5,
      timeUnit: '1s',
      duration: '1m',
      preAllocatedVUs: 10,
      maxVUs: 30,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.05'],
    'http_req_failed{scenario:recovery}': ['rate<0.01'],
    'http_req_duration{scenario:recovery}': ['p(95)<1000'],
    'checks{scenario:recovery}': ['rate>0.99'],
    dropped_iterations: ['count==0'],
  },
};

function request(scenario) {
  const requestId = `k6-spike-${Date.now()}-${exec.vu.idInTest}-${exec.scenario.iterationInTest}`;
  const res = http.post(
    `${BASE}/api/recommendations`,
    JSON.stringify({
      request_id: requestId,
      item_id: 'item-100',
      scenario: 'normal',
      provider: PROVIDER,
    }),
    {
      headers: { 'Content-Type': 'application/json' },
      tags: { name: 'recommendations', scenario },
    },
  );
  check(res, { 'status 200': (r) => r.status === 200 });
}

export function warmup() { request('warmup'); }
export function spike() { request('spike'); }
export function recovery() { request('recovery'); }
