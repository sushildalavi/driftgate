from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

DRIFT_DETECTION_LATENCY_SECONDS = Histogram(
    "drift_detection_latency_seconds",
    "Latency for /track drift detection pipeline",
)
ADVISORY_LOCK_WAIT_SECONDS = Histogram(
    "advisory_lock_wait_seconds",
    "Time waiting on advisory lock",
)
WEBHOOK_PUBLISH_LATENCY_SECONDS = Histogram(
    "webhook_publish_latency_seconds",
    "Webhook delivery latency",
)
OUTBOX_DELIVERY_LATENCY_SECONDS = Histogram(
    "outbox_delivery_latency_seconds",
    "Seconds from outbox creation to successful webhook delivery",
)
DLQ_SIZE = Gauge("dlq_size", "Current DLQ row count")
OUTBOX_PENDING_GAUGE = Gauge("outbox_pending_gauge", "Current pending webhook outbox rows")
DRIFT_COUNT_TOTAL = Counter("drift_count_total", "Drift count", ["severity", "endpoint_id"])
COMPATIBILITY_CLASSIFICATION_TOTAL = Counter(
    "compatibility_classification_total", "Compatibility classification count", ["classification"]
)
WEBHOOK_DELIVERY_FAILURES_TOTAL = Counter(
    "webhook_delivery_failures_total", "Webhook delivery failures"
)
KAFKA_PUBLISH_FAILURES_TOTAL = Counter(
    "kafka_publish_failures_total", "Kafka publish failures"
)


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
