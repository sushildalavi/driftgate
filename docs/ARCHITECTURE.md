# DriftGate Architecture

DriftGate has two backend paths:

1. Scheduled monitor (`backend/`): fetches configured APIs, infers schema, computes deterministic hash, stores snapshots/diffs.
2. Runtime guard (`app/`): accepts `POST /track` payloads, computes structural fingerprints, classifies drift, stores runtime violations.
3. Webhook gateway (`gateway/`): verifies signatures and idempotency before forwarding accepted payloads to the runtime service.
4. Event backend abstraction: publishes drift events to Kafka or Azure Service Bus when configured, with a no-op local fallback.
5. Document store: payload snapshots, schema diff documents, validation failures, and replay artifacts go to a MongoDB/Cosmos-compatible store when enabled.
6. Angular product site and app shell (`frontend/`): public landing page, schema registry, drift diff review, webhook reliability, contract review, and document-store inspection.

## Runtime Guard Data Path

1. `POST /track` receives payload.
2. Payload is normalized (`app/core/parser.py`).
3. Deterministic fingerprint is generated (SHA-256 over structural string).
4. Registration executes under transactional advisory lock (`pg_advisory_xact_lock`).
5. Snapshot is inserted with endpoint-scoped uniqueness:
   - `UNIQUE(endpoint_id, fingerprint)`.
6. Drift is classified into `SAFE`, `RISKY`, `BREAKING`.
7. Runtime metrics are exposed at `/api/v1/metrics`.
8. Drift events are handed off through an environment-selected backend (`EVENT_BACKEND`).
9. Document artifacts are written separately to MongoDB/Cosmos via `DOCUMENT_STORE_BACKEND`.

## Runtime Schema

Managed by SQL migrations in `migrations/`:

- `001_contract_guard_schema.sql`
- `002_runtime_snapshot_endpoint_fingerprint_unique.sql`
