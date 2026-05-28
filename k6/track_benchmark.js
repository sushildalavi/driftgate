import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    drift_load: {
      executor: 'constant-vus',
      vus: Number(__ENV.K6_VUS || 200),
      duration: __ENV.K6_DURATION || '25s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1500'],
  },
};

const BASE = __ENV.TRACK_URL || 'http://localhost:8018/track';
const FAIL_WEBHOOK = __ENV.FAIL_WEBHOOK === 'true';

function payloadVariant(i) {
  const p = {
    namespace: 'k6',
    service_name: 'bench-client',
    http_method: 'POST',
    route_path: '/bench/contracts',
    payload: {
      user_id: i,
      score: i % 3 === 0 ? 42.5 : 42,
      price: i % 5 === 0 ? 42 : 42.5,
      meta: i % 7 === 0 ? undefined : { active: true, tags: ['a', 'b'] },
    },
  };
  if (FAIL_WEBHOOK) {
    p.payload.webhook_failure_injected = true;
  }
  return p;
}

export default function () {
  const i = Math.floor(Math.random() * 5000);
  const body = JSON.stringify(payloadVariant(i));
  const res = http.post(BASE, body, { headers: { 'Content-Type': 'application/json' } });
  check(res, { 'status 200': (r) => r.status === 200 });
  sleep(0.01);
}
