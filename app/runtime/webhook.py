from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.runtime.metrics import DLQ_SIZE, WEBHOOK_DELIVERY_FAILURES_TOTAL, WEBHOOK_PUBLISH_LATENCY_SECONDS


async def upsert_dlq(
    db: AsyncSession,
    *,
    event_id: str,
    consumer_id: str,
    endpoint_id: str,
    target_url: str,
    payload: dict[str, Any],
    failure_reason: str,
    attempt_count: int,
) -> None:
    started = datetime.now(timezone.utc)
    await db.execute(
        text(
            """
            INSERT INTO webhook_delivery_dlq(
                event_id, consumer_id, endpoint_id, target_url, payload,
                failure_reason, attempt_count, last_attempt_at
            )
            VALUES (:event_id, :consumer_id, CAST(:endpoint_id AS uuid), :target_url,
                    CAST(:payload AS jsonb), :failure_reason, :attempt_count, NOW())
            ON CONFLICT (event_id, consumer_id)
            DO UPDATE SET
                failure_reason = EXCLUDED.failure_reason,
                attempt_count = GREATEST(webhook_delivery_dlq.attempt_count, EXCLUDED.attempt_count),
                last_attempt_at = NOW()
            """
        ),
        {
            "event_id": event_id,
            "consumer_id": consumer_id,
            "endpoint_id": endpoint_id,
            "target_url": target_url,
            "payload": json.dumps(payload),
            "failure_reason": failure_reason,
            "attempt_count": attempt_count,
        },
    )
    count_row = await db.execute(text("SELECT COUNT(*) FROM webhook_delivery_dlq"))
    DLQ_SIZE.set(float(count_row.scalar_one()))
    WEBHOOK_PUBLISH_LATENCY_SECONDS.observe((datetime.now(timezone.utc) - started).total_seconds())


async def deliver_with_retry(
    db: AsyncSession,
    *,
    event_id: str,
    endpoint_id: str,
    subscription: dict[str, Any],
    payload: dict[str, Any],
    max_attempts: int = 3,
    client: httpx.AsyncClient | None = None,
    persist_dlq: bool = True,
) -> bool:
    if not subscription.get("active", True):
        return False

    target_url = subscription["target_url"]
    consumer_id = subscription["consumer_id"]
    now = datetime.now(timezone.utc).isoformat()
    own_client = client is None
    http_client = client or httpx.AsyncClient(timeout=5)

    try:
        for attempt in range(1, max_attempts + 1):
            attempt_started = datetime.now(timezone.utc)
            try:
                res = await http_client.post(target_url, json=payload)
                if 200 <= res.status_code < 300:
                    await db.execute(
                        text(
                            """
                            INSERT INTO webhook_delivery_attempts(event_id, consumer_id, endpoint_id, target_url, success, failure_reason, attempt_count, attempted_at)
                            VALUES (:event_id, :consumer_id, CAST(:endpoint_id AS uuid), :target_url, TRUE, NULL, :attempt_count, NOW())
                            """
                        ),
                        {
                            "event_id": event_id,
                            "consumer_id": consumer_id,
                            "endpoint_id": endpoint_id,
                            "target_url": target_url,
                            "attempt_count": attempt,
                        },
                    )
                    await db.commit()
                    WEBHOOK_PUBLISH_LATENCY_SECONDS.observe((datetime.now(timezone.utc) - attempt_started).total_seconds())
                    return True
                reason = f"HTTP {res.status_code}"
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"

            WEBHOOK_DELIVERY_FAILURES_TOTAL.inc()
            await db.execute(
                text(
                    """
                    INSERT INTO webhook_delivery_attempts(event_id, consumer_id, endpoint_id, target_url, success, failure_reason, attempt_count, attempted_at)
                    VALUES (:event_id, :consumer_id, CAST(:endpoint_id AS uuid), :target_url, FALSE, :failure_reason, :attempt_count, NOW())
                    """
                ),
                {
                    "event_id": event_id,
                    "consumer_id": consumer_id,
                    "endpoint_id": endpoint_id,
                    "target_url": target_url,
                    "failure_reason": reason,
                    "attempt_count": attempt,
                },
            )
            if attempt == max_attempts:
                if persist_dlq:
                    await upsert_dlq(
                        db,
                        event_id=event_id,
                        consumer_id=consumer_id,
                        endpoint_id=endpoint_id,
                        target_url=target_url,
                        payload={"event": payload, "failed_at": now},
                        failure_reason=reason,
                        attempt_count=attempt,
                    )
                await db.commit()
                WEBHOOK_PUBLISH_LATENCY_SECONDS.observe((datetime.now(timezone.utc) - attempt_started).total_seconds())
                return False

        return False
    finally:
        if own_client:
            await http_client.aclose()
