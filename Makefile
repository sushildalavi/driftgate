PYTHON ?= python

.PHONY: test test-backend test-frontend test-runtime simulate demo docker-config runtime-up runtime-migrate

test: test-backend test-runtime test-frontend

test-backend:
	cd backend && pytest -q

test-runtime: runtime-up runtime-migrate
	$(PYTHON) -m pip install -q -r requirements.txt
	$(PYTHON) -m pytest -q tests/test_runtime_track.py

test-frontend:
	cd frontend && npm run build

runtime-up:
	docker compose up -d postgres runtime-guard

runtime-migrate:
	DATABASE_URL_SYNC=postgresql://schemapilot:dev@localhost:55433/schemapilot_runtime $(PYTHON) scripts/apply_runtime_migrations.py

simulate: runtime-up runtime-migrate
	TRACK_URL=http://localhost:8302/track \
	DATABASE_URL_SYNC=postgresql://schemapilot:dev@localhost:55433/schemapilot_runtime \
	SIM_REQUESTS=5000 \
	SIM_CONCURRENCY=200 \
	SIM_OUTPUT_PATH=docs/benchmarks/schema_pilot_simulation_5000.json \
	$(PYTHON) tests/simulate_drift.py

demo:
	docker compose up -d --build
	until curl -sf http://localhost:8301/health >/dev/null; do sleep 2; done
	curl -X POST http://localhost:8301/api/monitor/run-once -H "X-SCHEMAPILOT-ADMIN-SECRET: $${ADMIN_SECRET:-dev-secret}"
	curl http://localhost:8302/api/v1/metrics

docker-config:
	docker compose config
