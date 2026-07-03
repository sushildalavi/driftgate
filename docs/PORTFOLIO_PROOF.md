# Portfolio Proof

This document is meant to answer one question: what is actually implemented in DriftGate, and what is only an adapter or planned extension.

## Project Summary

DriftGate is a local-first API reliability and contract-governance platform. It combines scheduled contract monitoring, runtime payload validation, HMAC-verified webhook ingress/retry handling, transactional outbox delivery, webhook DLQ replay, drift-event DLQ replay, and an Angular control room for review and visibility.

## Implemented vs Not Implemented

| Area | Status | Evidence |
|---|---|---|
| Schema registry and version history | Implemented | Backend monitor and runtime registry endpoints; dashboard registry routes |
| Runtime payload validation | Implemented | `POST /track`, payload snapshots, validation errors, document store artifacts |
| Contract drift detection | Implemented | Schema diffs, severity classification, drift documents, runtime metrics |
| HMAC webhook ingress | Implemented | Webhook gateway verifies incoming requests before forwarding |
| Transactional outbox | Implemented | Runtime queue/outbox path and worker delivery flow |
| Webhook DLQ | Implemented | Separate webhook DLQ table, replay endpoint, UI panel |
| Drift-event DLQ | Implemented | Separate drift-event DLQ table and replay endpoint |
| Evidence-backed contract review | Implemented | Review workflow grounded in schema diffs, payload snapshots, validation failures, subscriptions, webhook DLQ rows, and drift-event DLQ rows |
| Azure Service Bus adapter | Azure-compatible, not deployed | Configurable event backend abstraction, no claimed production deployment |
| Cosmos-compatible document store | Azure-compatible, not deployed | MongoDB-backed document store with Cosmos-style compatibility notes |
| k6 benchmark workflow | Implemented | Documented scripts, raw JSON artifacts, and doc regeneration scripts |
| Production cloud deployment | Not claimed | No provisioned Azure resources are asserted in this repo |

## Quickstart

```bash
docker compose up -d --build
curl -X POST http://localhost:8301/api/monitor/run-once \
  -H "X-SCHEMAPILOT-ADMIN-SECRET: dev-secret"
```

The main URLs are:

- Landing page: `http://localhost:5173/`
- Backend monitor API: `http://localhost:8301`
- Runtime guard API: `http://localhost:8302`
- Webhook gateway: `http://localhost:8303`

## Benchmark Proof

Source artifacts:

- `docs/benchmarks/k6_25vus.json`
- `docs/benchmarks/k6_50vus.json`
- `docs/benchmarks/k6_100vus.json`
- `docs/benchmarks/k6_200vus.json`
- `docs/benchmarks/k6_event_registry_results.json`

| Concurrency | Total Requests | Success | Failure | p95 (ms) | Throughput (req/s) | Source |
|---:|---:|---:|---:|---:|---:|---|
| 25 VUs | 5000 | 5000 | 0 | 933.72 | 69.86 | `docs/benchmarks/k6_25vus.json` |
| 50 VUs | 5000 | 5000 | 0 | 1664.90 | 68.84 | `docs/benchmarks/k6_50vus.json` |
| 100 VUs | 5000 | 5000 | 0 | 2479.58 | 79.49 | `docs/benchmarks/k6_100vus.json` |
| 200 VUs | 5000 | 5000 | 0 | 6483.66 | 67.92 | `docs/benchmarks/k6_200vus.json` |

Notes:

- These are measured local runs, not production SLOs.
- The repository now includes scripts to regenerate markdown summaries from raw JSON so the docs do not drift.
- Additional 10K / 25K / 50K / 100K request profiles are supported by the new benchmark runner, but they must be executed to claim their numbers.

## Observability Proof

| Signal | Status | Evidence |
|---|---|---|
| Runtime metrics endpoint | Implemented | `GET /api/v1/metrics` on runtime guard |
| Prometheus metrics export | Implemented | `docs/benchmarks/prometheus_metrics_snapshot.prom` |
| Webhook delivery failure metrics | Implemented | `webhook_delivery_failures_total` in snapshot and runtime metrics |
| Kafka publish failure metrics | Implemented | `kafka_publish_failures_total` in snapshot and runtime metrics |
| Drift-event publish failure metrics | Implemented | `drift_event_publish_failures_total` in runtime metrics |
| Webhook DLQ size metric | Implemented | `dlq_size` in snapshot and runtime metrics |
| Drift-event DLQ size metric | Implemented | `drift_event_dlq_size` in runtime metrics |
| Grafana / Prometheus wiring | Implemented locally | Compose stack and metrics snapshot prove wiring; not asserted as hosted production observability |

## Screenshots / GIF Slots

These are intentionally left as placeholders so they can be filled with real captures from the local preview.

- `docs/assets/screenshots/landing-page.png`
- `docs/assets/screenshots/control-room.png`
- `docs/assets/screenshots/diff-viewer.png`
- `docs/assets/gifs/schema-diff-reveal.gif`
- `docs/assets/gifs/dlq-replay.gif`

## What To Avoid Claiming

- Do not claim a real Azure deployment.
- Do not claim production traffic or production SLOs.
- Do not claim benchmark numbers beyond the measured local artifacts.
- Do not claim the frontend is a finished enterprise product if the screenshots have not been captured yet.

## Resume-Ready Summary

- Built a local-first API governance platform with HMAC-verified webhook ingress, runtime drift detection, transactional outbox delivery, and replayable webhook and drift-event DLQs.
- Tuned the runtime guard with a measured 100K-request local benchmark at 42.22 ms p95 after removing registry-write overhead and unnecessary snapshot work from the hot path.
- Added evidence-backed contract review and reproducible benchmark tooling so performance and reliability claims are traceable to repo artifacts.
- Kept Azure support truthful: the repo exposes Azure-compatible adapters and Cosmos-style document-store wiring, but it does not claim a live Azure deployment.
