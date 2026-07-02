import http from 'k6/http';
import { Counter } from 'k6/metrics';
import { check } from 'k6';

const requestErrorTransportTotal = new Counter('request_error_transport_total');
const requestErrorValidationTotal = new Counter('request_error_validation_total');
const requestErrorClientTotal = new Counter('request_error_client_total');
const requestErrorServerTotal = new Counter('request_error_server_total');

export const options = {
  scenarios: {
    drift_profile: {
      executor: 'shared-iterations',
      vus: Number(__ENV.K6_VUS || 25),
      iterations: Number(__ENV.K6_TOTAL_REQUESTS || 10000),
      maxDuration: __ENV.K6_MAX_DURATION || '45m',
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<2000'],
  },
};

const TRACK_URL = __ENV.TRACK_URL || 'http://localhost:8302/track';
const ROUTE_PATH = __ENV.ROUTE_PATH || '/bench/profile';
const SERVICE_NAME = __ENV.SERVICE_NAME || 'bench-profile';
const NAMESPACE = __ENV.NAMESPACE || 'k6';
const HTTP_METHOD = __ENV.HTTP_METHOD || 'POST';

function payloadVariant(i) {
  return {
    namespace: NAMESPACE,
    service_name: SERVICE_NAME,
    http_method: HTTP_METHOD,
    route_path: ROUTE_PATH,
    payload: {
      user_id: i,
      score: i % 3 === 0 ? 42.5 : 42,
      price: i % 5 === 0 ? 42 : 42.5,
      meta: i % 7 === 0 ? undefined : { active: true, tags: ['a', 'b'] },
    },
  };
}

export default function () {
  const i = __ITER + __VU * 1000;
  const res = http.post(TRACK_URL, JSON.stringify(payloadVariant(i)), {
    headers: { 'Content-Type': 'application/json' },
  });
  if (res.status === 0) {
    requestErrorTransportTotal.add(1);
  } else if (res.status === 422) {
    requestErrorValidationTotal.add(1);
  } else if (res.status >= 400 && res.status < 500) {
    requestErrorClientTotal.add(1);
  } else if (res.status >= 500) {
    requestErrorServerTotal.add(1);
  }
  check(res, {
    'status 200': (r) => r.status === 200,
    'no server error': (r) => r.status < 500,
  });
}
