# Runtime Simulation Benchmarks

## 5000-request simulation

Run:

```bash
make simulate
```

Artifact output:

- `docs/benchmarks/schema_pilot_simulation_5000.json`

The JSON includes:

- `events_total`
- `concurrency`
- `success_count`
- `failure_count`
- `safe_count`
- `risky_count`
- `breaking_count`
- `duplicate_baselines`
- `duration_seconds`
- `command_used`
- `timestamp`

## Canonical k6 Runtime Benchmark

Run against runtime guard service:

```bash
k6 run --vus 200 --duration 60s k6/benchmark.js
```

Optional explicit target:

```bash
TRACK_URL=http://localhost:8018/track k6 run --vus 200 --duration 60s k6/benchmark.js
```
