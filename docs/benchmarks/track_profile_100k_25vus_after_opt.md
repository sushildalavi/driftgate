# DriftGate Benchmark Summary

| artifact | VUs | requests | failed checks | p50 latency ms | p95 latency ms | p99 latency ms | error rate | throughput rps | error classes | state snapshot |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| track_profile_100k_25vus_after_opt.json | 25 | 100000 | 0 | 15.479 | 42.226049999999994 | 62.958569999999945 | 0 | 1299.0882414132054 | transport:0, validation:0, client:0, server:0 | endpoint_count=1, snapshot_count=0, schema_version_count=8, webhook_outbox_pending_count=0, webhook_delivery_dlq_count=0, drift_event_dlq_count=0, webhook_delivery_attempts_count=0 |
