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

- Main monitor API (backend service): `http://localhost:8080`
- Runtime guard API (benchmark target): `http://localhost:8018`
- Runtime track: `POST http://localhost:8018/track`
- Runtime metrics: `GET http://localhost:8018/api/v1/metrics`
- Scheduled backend docs: `http://localhost:8080/docs`
- Frontend dashboard: `http://localhost:5174`

## Common Pitfall

- `http://localhost:8000` is frequently occupied by other local projects.
- Use `http://localhost:8018/track` for SchemaPilot runtime benchmarks unless you intentionally remap ports.
