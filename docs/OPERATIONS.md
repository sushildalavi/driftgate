# Operations

## Local verification

```bash
make docker-config
make test
make simulate
```

## Runtime guard only

```bash
docker compose up -d postgres runtime-guard
DATABASE_URL_SYNC=postgresql://schemapilot:dev@localhost:55433/schemapilot_runtime \
python scripts/apply_runtime_migrations.py
```

## Endpoints

- Main monitor API (backend service): `http://localhost:8301`
- Webhook gateway: `http://localhost:8303`
- Runtime guard API (benchmark target): `http://localhost:8302`
- Runtime track forwarded by gateway: `POST http://localhost:8303/webhooks/<source>`
- Runtime track: `POST http://localhost:8302/track`
- Runtime metrics: `GET http://localhost:8302/api/v1/metrics`
- Scheduled backend docs: `http://localhost:8301/docs`
- Angular dashboard: `http://localhost:5173`

## Common Pitfall

- `http://localhost:8000` is frequently occupied by other local projects.
- Use `http://localhost:8302/track` for DriftGate runtime benchmarks unless you intentionally remap ports.
