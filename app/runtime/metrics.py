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
DRIFT_EVENT_PUBLISH_FAILURES_TOTAL = Counter(
    "drift_event_publish_failures_total", "Failed drift-event publications"
)
DRIFT_EVENT_DLQ_SIZE = Gauge("drift_event_dlq_size", "Current drift-event DLQ row count")
CONTRACT_REVIEW_LATENCY_SECONDS = Histogram(
    "contract_review_latency_seconds",
    "Latency for the contract review workflow",
)
CONTRACT_REVIEW_TOTAL = Counter(
    "contract_review_total",
    "Contract review outcomes",
    ["decision", "severity", "provider"],
)
CONTRACT_REVIEW_INSUFFICIENT_EVIDENCE_TOTAL = Counter(
    "contract_review_insufficient_evidence_total",
    "Contract reviews that returned insufficient evidence",
    ["provider"],
)
CONTRACT_REVIEW_SCHEMA_VALID_TOTAL = Counter(
    "contract_review_schema_valid_total",
    "Contract review outputs that passed schema validation",
    ["provider"],
)
CONTRACT_REVIEW_GROUNDING_FAILURE_TOTAL = Counter(
    "contract_review_grounding_failure_total",
    "Contract review outputs rejected for evidence grounding failures",
    ["provider"],
)


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
