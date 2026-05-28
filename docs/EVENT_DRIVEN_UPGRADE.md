# Event-Driven Contract Registry Upgrade

## Status
- Implemented: compatibility classifier, endpoint-scoped schema registry versions, consumer subscriptions, event publishing abstraction, webhook retry+DLQ, Prometheus metrics endpoint, Grafana dashboard config, k6 script.
- Incomplete: real Kafka broker integration wiring (default publisher is currently no-op unless custom producer is injected).

## Architecture

```mermaid
flowchart LR
  C[Client Middleware] --> T[/track]
  T --> Canonical[Canonicalize + Fingerprint]
  Canonical --> Registry[Versioned Registry Write + Advisory Lock]
  Registry --> Diff[Compatibility Diff Classifier]
  Diff --> Subs[Subscription Router]
  Diff --> Kafka[drift.detected publisher]
  Subs --> Webhook[Webhook Delivery Worker]
  Webhook --> DLQ[(DLQ)]
  T --> Metrics[/metrics]
```

## Compatibility Rules

- Adding optional field: `SAFE`
- Adding required field: `FORWARD_COMPATIBLE`
- Removing required field: `BREAKING`
- Removing optional field: `RISKY`
- Required becomes nullable: `BACKWARD_COMPATIBLE`
- Nullable becomes required: `BREAKING`
- integer -> number: `RISKY`
- number -> integer: `BREAKING`
- string -> number/integer: `BREAKING`
- enum expansion: `FORWARD_COMPATIBLE`
- enum contraction: `BREAKING`
- nested object mutations: recursive path-level detection
- array item type mutation: `BREAKING`

## Event Schema (`drift.detected`)

Fields:
- `event_id`
- `endpoint_id`
- `endpoint_path_name`
- `namespace`
- `old_fingerprint`
- `new_fingerprint`
- `old_version`
- `new_version`
- `severity`
- `compatibility_classification`
- `timestamp`
- `schema_diff_summary`
- `affected_consumer_count`

## Observability
- `/metrics` exposes Prometheus format.
- Dashboard JSON: `grafana/dashboards/schemapilot-runtime-dashboard.json`

## Benchmark
- k6 script: `k6/track_benchmark.js`
- runbook: `docs/benchmarks/K6_RUN.md`
- actual numeric claims must come from committed summary output.
