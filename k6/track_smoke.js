import http from 'k6/http';
import { check } from 'k6';

export const options = {
  summaryTrendStats: ["avg","min","med","max","p(90)","p(95)","p(99)"],
  vus: 5,
  iterations: 100,
};

const URL = __ENV.TRACK_URL || 'http://localhost:8018/track';

export default function () {
  const payload = {
    namespace: 'k6',
    service_name: 'smoke-client',
    http_method: 'POST',
    route_path: '/smoke/contracts',
    payload: { user_id: __VU, score: __ITER % 2 === 0 ? 42 : 42.5, meta: { active: true } },
  };
  const res = http.post(URL, JSON.stringify(payload), { headers: { 'Content-Type': 'application/json' } });
  check(res, { 'status is 200': (r) => r.status === 200 });
}
