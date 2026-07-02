import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 200,
  duration: '60s',
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

const TRACK_URL = __ENV.TRACK_URL || 'http://localhost:8302/track';

export default function () {
  const payload = JSON.stringify({
    namespace: 'k6',
    service_name: 'payment-service',
    http_method: 'POST',
    route_path: `/invoice/${Math.floor(Math.random() * 50)}`,
    payload: {
      amount: Math.random() * 1000,
      currency: 'USD',
      customer_id: `cust_${Math.floor(Math.random() * 100)}`,
    },
  });

  const res = http.post(TRACK_URL, payload, {
    headers: { 'Content-Type': 'application/json' },
  });

  check(res, {
    'status 200': (r) => r.status === 200,
    'no server error': (r) => r.status !== 500,
  });
}
