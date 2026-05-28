from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Protocol

from app.runtime.metrics import KAFKA_PUBLISH_FAILURES_TOTAL
from app.runtime.models import DriftEvent

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    async def publish_drift_detected(self, event: DriftEvent) -> None:
        ...


class NoopEventPublisher:
    async def publish_drift_detected(self, event: DriftEvent) -> None:
        return


class KafkaEventPublisher:
    def __init__(self, producer: object, topic: str = "drift.detected") -> None:
        self._producer = producer
        self._topic = topic

    async def publish_drift_detected(self, event: DriftEvent) -> None:
        payload = {
            "event_id": event.event_id,
            "endpoint_id": event.endpoint_id,
            "endpoint_path_name": event.endpoint_name,
            "namespace": event.namespace,
            "old_fingerprint": event.old_fingerprint,
            "new_fingerprint": event.new_fingerprint,
            "old_version": event.old_version,
            "new_version": event.new_version,
            "severity": event.severity,
            "compatibility_classification": event.compatibility_classification,
            "timestamp": event.timestamp,
            "schema_diff_summary": event.schema_diff_summary,
            "affected_consumer_count": event.affected_consumer_count,
        }
        blob = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        await self._producer.send_and_wait(self._topic, blob)


async def publish_with_retry(publisher: EventPublisher, event: DriftEvent, retries: int = 3) -> None:
    wait = 0.05
    for attempt in range(1, retries + 1):
        try:
            await publisher.publish_drift_detected(event)
            return
        except Exception:
            if attempt == retries:
                raise
            await asyncio.sleep(wait)
            wait *= 2


def publish_fire_and_forget(publisher: EventPublisher, event: DriftEvent) -> None:
    async def _run() -> None:
        try:
            await publish_with_retry(publisher, event)
        except Exception:
            KAFKA_PUBLISH_FAILURES_TOTAL.inc()
            logger.exception("Kafka publish failed for event_id=%s", event.event_id)

    asyncio.create_task(_run())


def build_default_publisher() -> EventPublisher:
    enabled = os.getenv("KAFKA_ENABLED", "false").lower() == "true"
    if not enabled:
        return NoopEventPublisher()

    # Local docker default: single-broker durability/perf tradeoff.
    _acks = os.getenv("KAFKA_ACKS", "1")
    if _acks != "1":
        os.environ["KAFKA_ACKS"] = "1"

    return NoopEventPublisher()
