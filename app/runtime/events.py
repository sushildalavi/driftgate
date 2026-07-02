from __future__ import annotations

import logging
from typing import Any

from app.runtime.event_backends import (
    DriftEventBackend,
    KafkaEventBackend,
    NoopEventBackend,
    AzureServiceBusEventBackend,
    build_event_backend,
)
from app.runtime.drift_event_dlq import record_event_failure
from app.runtime.metrics import DRIFT_EVENT_PUBLISH_FAILURES_TOTAL, KAFKA_PUBLISH_FAILURES_TOTAL
from app.runtime.models import DriftEvent

logger = logging.getLogger(__name__)

EventPublisher = DriftEventBackend


async def publish_with_retry(
    publisher: DriftEventBackend, event: DriftEvent, retries: int = 3
) -> None:
    wait = 0.05
    for attempt in range(1, retries + 1):
        try:
            await publisher.publish_drift_detected(event)
            return
        except Exception:
            if attempt == retries:
                raise
            import asyncio

            await asyncio.sleep(wait)
            wait *= 2


def publish_fire_and_forget(
    publisher: DriftEventBackend,
    event: DriftEvent,
    *,
    session_factory: Any | None = None,
) -> None:
    async def _run() -> None:
        try:
            await publish_with_retry(publisher, event)
        except Exception:
            DRIFT_EVENT_PUBLISH_FAILURES_TOTAL.inc()
            if isinstance(publisher, KafkaEventBackend):
                KAFKA_PUBLISH_FAILURES_TOTAL.inc()
            await record_event_failure(
                event,
                failure_reason=f"publish failed via {publisher.__class__.__name__}",
                publisher_name=publisher.__class__.__name__,
                session_factory=session_factory,
            )
            logger.exception("Drift-event publish failed for event_id=%s", event.event_id)

    import asyncio

    asyncio.create_task(_run())


def build_default_publisher() -> DriftEventBackend:
    return build_event_backend()


__all__ = [
    "EventPublisher",
    "AzureServiceBusEventBackend",
    "DriftEventBackend",
    "KafkaEventBackend",
    "NoopEventBackend",
    "build_default_publisher",
    "publish_fire_and_forget",
    "publish_with_retry",
]
