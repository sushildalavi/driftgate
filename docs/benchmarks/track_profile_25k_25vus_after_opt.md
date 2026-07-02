# DriftGate Benchmark Summary

| artifact | VUs | requests | failed checks | p50 latency ms | p95 latency ms | p99 latency ms | error rate | throughput rps | error classes | state snapshot |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| track_profile_25k_25vus_after_opt.json | 25 | 25000 | 0 | 17.826 | 48.26449999999999 | 77.68154999999999 | 0 | 1154.154614984177 | transport:0, validation:0, client:0, server:0 | endpoint_count=1, snapshot_count=0, schema_version_count=8, webhook_outbox_pending_count=0, webhook_delivery_dlq_count=0, drift_event_dlq_count=0, webhook_delivery_attempts_count=0 |
