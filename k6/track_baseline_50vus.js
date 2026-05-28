import http from 'k6/http';
import { check } from 'k6';

export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: { s: { executor: 'shared-iterations', vus: 50, iterations: 5000, maxDuration: '20m' } },
};
const URL = __ENV.TRACK_URL || 'http://localhost:8018/track';
export default function () {
  const i = __ITER;
  const body = { namespace: 'k6', service_name: 'bench-client', http_method: 'POST', route_path: '/bench/contracts', payload: { user_id: i, score: i % 3 === 0 ? 42.5 : 42, price: i % 5 === 0 ? 42 : 42.5, meta: i % 7 === 0 ? null : { active: true } } };
  const r = http.post(URL, JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });
  check(r, { 'status 200': (res) => res.status === 200 });
}
