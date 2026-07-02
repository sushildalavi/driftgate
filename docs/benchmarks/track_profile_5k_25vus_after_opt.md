# DriftGate Benchmark Summary

| artifact | VUs | requests | failed checks | p50 latency ms | p95 latency ms | p99 latency ms | error rate | throughput rps | error classes | state snapshot |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| track_profile_5k_25vus_after_opt.json | 25 | 5000 | 0 | 18.2365 | 35.155849999999994 | 60.68977999999964 | 0 | 1180.9989550521245 | transport:0, validation:0, client:0, server:0 | endpoint_count=1, snapshot_count=0, schema_version_count=8, webhook_outbox_pending_count=0, webhook_delivery_dlq_count=0, drift_event_dlq_count=0, webhook_delivery_attempts_count=0 |
