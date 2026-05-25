# SchemaPilot — API Contract Drift Monitor

SchemaPilot is a contract-observability system for JSON APIs.

It gives you two complementary capabilities in this repo:

1. **Scheduled Drift Monitor (main product path)**
- Polls live endpoints from a registry.
- Infers response schemas from observed payloads.
- Computes deterministic schema hashes.
- Diffs schema evolution and classifies severity.
- Powers a React dashboard for operations and triage.

2. **Runtime Contract Guard (new precision path)**
- Accepts middleware-submitted payload samples in real time.
- Normalizes payload structure into deterministic AST-like fingerprints.
- Uses PostgreSQL advisory locks for safe concurrent writes.
- Records SAFE / RISKY / BREAKING violations at runtime.

---

## Screenshots (Playwright-generated)

### Dashboard Overview
![Dashboard](docs/screenshots/01-dashboard.png)

### Dashboard Lower Panels (Endpoints + Trends)
![Dashboard Lower](docs/screenshots/02-dashboard-lower.png)

### Endpoint Detail (Diffs)
![Endpoint Detail](docs/screenshots/03-endpoint-detail.png)

### Schema Viewer
![Schema Viewer](docs/screenshots/04-schema-viewer.png)

### Diff History
![Diff History](docs/screenshots/05-diff-history.png)

---

## Why SchemaPilot

In distributed systems, services evolve independently and break consumers silently.
SchemaPilot detects response-contract drift from **live traffic behavior**, not static docs.

Key properties:
- Deterministic drift classification (not LLM-decided)
- Field-level schema diffing
- Concurrency-safe ingestion (advisory lock path)
- Snapshot history + UI for forensic analysis

---

## Architecture

```mermaid
flowchart LR
  subgraph Sources
    E1[Public APIs]
    E2[Internal APIs]
    E3[Drift Simulator]
  end

  subgraph Backend[FastAPI Backend]
    M1[Scheduled Monitor Worker]
    M2[Schema Infer + Hash + Diff]
    M3[Severity Classifier]
    M4[Changelog Generator]
    M5[Runtime Contract Guard /track]
  end

  DB[(PostgreSQL)]
  FE[React Dashboard]

  E1 --> M1
  E2 --> M1
  E3 --> M1

  M1 --> M2 --> M3 --> DB
  M4 --> DB
  M5 --> DB

  FE -->|REST| Backend
```

---

## Drift Decision Flow

```mermaid
flowchart TD
  A[Normalized old schema] --> C[Schema diff]
  B[Normalized new schema] --> C

  C --> D{Field missing?}
  D -- Yes --> D1[BREAKING]
  D -- No --> E{New field only?}
  E -- Yes --> E1[SAFE]
  E -- No --> F{Primitive changed?}

  F -- int -> float --> F1[RISKY]
  F -- float -> int --> F2[BREAKING]
  F -- other type change --> F3[BREAKING]

  C --> G{Nullability/type/array shape changed?}
  G --> H[Classify + persist violation]
```

---

## Data Model (High Level)

```mermaid
erDiagram
  api_endpoints ||--o{ schema_snapshots : has
  api_endpoints ||--o{ schema_diffs : has
  api_endpoints ||--o{ contract_drift_violations : has

  monitor_runs ||--o{ schema_snapshots : produces
  schema_snapshots ||--o{ schema_diffs : compared_in

  api_endpoints {
    UUID id PK
    TEXT name
    TEXT provider
    TEXT url
    TEXT method
  }

  schema_snapshots {
    UUID id PK
    UUID endpoint_id FK
    TEXT schema_hash
    JSONB normalized_schema_json
    TIMESTAMPTZ created_at
  }

  schema_diffs {
    UUID id PK
    UUID endpoint_id FK
    TEXT severity
    TEXT change_type
    TEXT path
    TIMESTAMPTZ created_at
  }

  contract_drift_violations {
    UUID id PK
    UUID endpoint_id FK
    VARCHAR observed_fingerprint
    ENUM severity
    JSONB diff_payload
    TIMESTAMPTZ detected_at
  }
```

---

## Repository Layout

- `backend/` — primary FastAPI monitor product, models, worker, API routes, tests
- `frontend/` — React dashboard and visual components
- `config/apis.yaml` — endpoint registry for scheduled monitor
- `drift-simulator/` — changing API payload source for local drift demos
- `docs/screenshots/` — Playwright screenshots
- `app/` — runtime contract-guard module (`/track`, metrics, parser/engine)
- `migrations/001_contract_guard_schema.sql` — runtime guard schema DDL
- `tests/simulate_drift.py` — 5000-request concurrency simulation harness

---

## Local Run (Main Product Path)

### Prerequisites
- Docker / Docker Compose
- Node.js (only needed if you run screenshot generation locally outside Docker)

### Start stack

```bash
docker compose up -d --build
```

### Trigger monitor manually

```bash
curl -X POST http://localhost:8080/api/monitor/run-once \
  -H "X-SCHEMAPILOT-ADMIN-SECRET: dev-secret"
```

### Open UI

- Dashboard: `http://localhost:5174`
- API docs: `http://localhost:8080/docs`

### Ports
- Frontend: `5174`
- Backend: `8080`
- Drift simulator: `8001`

---

## Runtime Contract Guard Path

The runtime guard module lives under `app/` and exposes:

- `POST /track` — submit live payload sample for schema-fingerprint + drift evaluation
- `GET /api/v1/metrics` — runtime counts (`endpoint_count`, `snapshot_count`, `severity_counts`)

Run it directly:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt asyncpg httpx uvicorn greenlet

# Requires postgres reachable by DATABASE_URL
DATABASE_URL='postgresql+asyncpg://schemapilot:dev@localhost:55432/schemapilot' \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8018
```

Sample request:

```bash
curl -X POST http://127.0.0.1:8018/track \
  -H 'content-type: application/json' \
  -d '{
    "service_name": "orders",
    "http_method": "POST",
    "route_path": "/v1/orders",
    "payload": {"order_id": 101, "price": 42.5, "items": [{"sku": "abc"}]}
  }'
```

Metrics endpoint:

```bash
curl http://127.0.0.1:8018/api/v1/metrics
```

---

## Severity Semantics

- `SAFE`: additive fields / non-breaking extensions
- `RISKY`: widening changes (example: `int -> float`)
- `BREAKING`: removals, narrowing changes (example: `float -> int`), incompatible type mutations

---

## Concurrency and Locking

Runtime registration uses a deterministic route hash and transactional advisory lock:

- lock id = hash(route_path)
- `SELECT pg_advisory_xact_lock(:lock_id)`
- serialized endpoint/snapshot insertion under high parallel ingestion

This prevents duplicate endpoint races and write collisions during concurrent submissions.

---

## Testing and Validation

### Existing backend tests

```bash
cd backend
pytest -q
```

### Runtime stress harness

```bash
# Uses tests/simulate_drift.py, defaults to 5000 requests
# Set TRACK_URL inside the script call context if needed.
```

The harness validates:
- request success under concurrency
- endpoint/snapshot persistence
- non-empty `SAFE`, `RISKY`, `BREAKING` counters
- `/api/v1/metrics` consistency

---

## Regenerating Screenshots (Playwright)

```bash
# Requires frontend running at http://localhost:5174
node take-screenshots.mjs
```

Outputs:
- `docs/screenshots/01-dashboard.png`
- `docs/screenshots/02-dashboard-lower.png`
- `docs/screenshots/03-endpoint-detail.png`
- `docs/screenshots/04-schema-viewer.png`
- `docs/screenshots/05-diff-history.png`

---

## Deployment Notes

- See [DEPLOY.md](DEPLOY.md) for deployment details.
- Main product architecture in this repo targets Cloud Run + Vercel + Postgres-style deployment.
- Runtime guard module can be deployed as a separate service if you want middleware ingestion decoupled from scheduled monitoring.

---

## Current Status

- Main monitor + dashboard pipeline: implemented
- Runtime contract guard + advisory lock ingestion: implemented
- End-to-end 5000-request simulation: passing in isolated validation setup
