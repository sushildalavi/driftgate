from app.runtime.metrics import (
    COMPATIBILITY_CLASSIFICATION_TOTAL,
    DRIFT_COUNT_TOTAL,
    DRIFT_EVENT_PUBLISH_FAILURES_TOTAL,
    WEBHOOK_DELIVERY_FAILURES_TOTAL,
)


def test_metrics_counters_increment():
    DRIFT_COUNT_TOTAL.labels(severity="RISKY", endpoint_id="ep1").inc()
    COMPATIBILITY_CLASSIFICATION_TOTAL.labels(classification="RISKY").inc()
    WEBHOOK_DELIVERY_FAILURES_TOTAL.inc()
    DRIFT_EVENT_PUBLISH_FAILURES_TOTAL.inc()

    assert DRIFT_COUNT_TOTAL.labels(severity="RISKY", endpoint_id="ep1")._value.get() >= 1
    assert COMPATIBILITY_CLASSIFICATION_TOTAL.labels(classification="RISKY")._value.get() >= 1
    assert WEBHOOK_DELIVERY_FAILURES_TOTAL._value.get() >= 1
    assert DRIFT_EVENT_PUBLISH_FAILURES_TOTAL._value.get() >= 1
