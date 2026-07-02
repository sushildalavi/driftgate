# DriftGate Benchmark Summary

| artifact | VUs | requests | failed checks | p50 latency ms | p95 latency ms | p99 latency ms | error rate | throughput rps | error classes | state snapshot |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| track_profile_25k_25vus.json | 25 | 25000 | 22027 | 0 | 740.3695999999999 | 2045.2893399999991 | 0.88108 | 191.86826085757932 | transport:0, validation:0, client:0, server:0 | endpoint_count=1, snapshot_count=0, schema_version_count=8, webhook_outbox_pending_count=0, webhook_delivery_dlq_count=0, drift_event_dlq_count=0, webhook_delivery_attempts_count=0 |
