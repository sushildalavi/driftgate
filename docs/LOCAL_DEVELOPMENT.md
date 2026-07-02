# Local Development

Everything here runs locally with Docker — no cloud account or paid service required.

## Prerequisites

- Docker + Docker Compose
- Python 3.11+
- Node.js 20+

## Full stack via Docker Compose

```bash
docker compose up -d --build
```

This brings up Postgres, the runtime guard, the webhook gateway, MongoDB (document
store), and the Angular product site + app console. The landing page is served at
`http://localhost:4200/` and the application shell starts at `/app/overview`.
Validate the compose file itself with:

```bash
docker compose config
```

Trigger a one-off monitor run and check runtime metrics:

```bash
curl -X POST http://localhost:8080/api/monitor/run-once \
  -H "X-SCHEMAPILOT-ADMIN-SECRET: dev-secret"
curl http://localhost:8018/api/v1/metrics
```

## Running services individually

### Backend (scheduled monitor, `backend/`)

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

### Runtime guard + root tests (`app/`, `tests/`)

```bash
pip install -r requirements.txt
python -m compileall app backend/app scripts
python -m pytest tests -q
```

To run the runtime guard against a live local Postgres via Docker:

```bash
make runtime-up        # starts postgres + runtime-guard containers
make runtime-migrate    # applies runtime SQL migrations
python -m pytest -q tests/test_runtime_track.py
```

### Webhook gateway (`gateway/`)

```bash
cd gateway
npm install
npm test
npm run build
```

### Angular dashboard (`frontend/`)

```bash
cd frontend
npm install
npm run lint
npm test -- --watch=false --browsers=ChromeHeadless
npm run build
```

For a guided demo flow, open:

- `/` for the public landing page
- `/app/overview` for the control center
- `/app/review` for the contract review workflow

## Makefile shortcuts

```bash
make test            # backend + runtime + frontend build
make test-backend    # backend/ pytest only
make test-runtime    # runtime-up, migrate, then runtime pytest
make docker-config   # docker compose config
make simulate        # runs the drift simulator against a local runtime guard
make demo            # docker compose up, seeds a monitor run, prints metrics
```

## Environment variables

See `.env.example` for the full list. The ones most relevant to local development:

| Variable | Purpose | Local default |
|---|---|---|
| `DATABASE_URL` / `DATABASE_URL_SYNC` | Postgres connection (async/sync) | local compose Postgres |
| `EVENT_BACKEND` | `noop`, `kafka`, or `azure_service_bus` | `noop` |
| `DOCUMENT_STORE_BACKEND` | `memory` or `mongo` | `memory` (tests), `mongo` (compose) |
| `DOCUMENT_STORE_URI` | Mongo/Cosmos connection string | `mongodb://mongo:27017` |
| `FRONTEND_ORIGINS` | CORS allow-list for the Angular dashboard | `http://localhost:4200` |
| `ADMIN_SECRET` | Header value required for admin endpoints | `dev-secret` |

## Load testing locally

k6 scripts live under `k6/` and target the runtime guard's `/track` endpoint. See
`docs/BENCHMARKS.md` for documented results and `docs/benchmarks/K6_RUN.md` for the
execution runbook. Nothing in `k6/` requires cloud infrastructure — point `TRACK_URL` at
your local compose stack.
