# Runtime Simulation Benchmarks

Raw benchmark JSON is the source of truth. Use `scripts/render_benchmark_docs.py` or `scripts/summarize_benchmarks.py` to regenerate Markdown from the stored artifacts.

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

The current benchmark suite includes the finalized 25/50/100/200-VU tiers in `docs/benchmarks/K6_RESULTS.md`.
Use `python scripts/run_k6_benchmark.py --script k6/track_profile.js ...` to generate additional request-volume profiles.

Recommended profile steps:

- 10K requests at 25 VUs
- 25K requests at 25 VUs
- 50K requests at 50 VUs
- 100K requests at 100 VUs
- 250K requests at 200 VUs

The runner emits raw JSON, a state snapshot, and a Markdown summary from the same run. Do not hand-edit the JSON.

## Smoke test result (measured, 2026-07-01)

Run against the full local Docker Compose stack (`docker compose up -d --build`):

```bash
TRACK_URL=http://localhost:8302/track k6 run k6/track_smoke.js
```

100 iterations, 5 VUs, all against `POST /track`:

| Metric | Value |
|---|---|
| Requests | 100 |
| Failures | 0 (0.00%) |
| Throughput | ~434 req/s |
| `http_req_duration` avg | 11.3 ms |
| `http_req_duration` p90 | 8.1 ms |
| `http_req_duration` p95 | 26.1 ms |
| `http_req_duration` p99 | 129.7 ms |

This is a smoke-scale result, not a load test — see the 200-VU k6 results above for
sustained throughput numbers. No larger run beyond what's documented above has been
performed on this machine.
