from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.db import SessionLocal
from app.runtime.metrics import OUTBOX_DELIVERY_LATENCY_SECONDS, OUTBOX_PENDING_GAUGE
from app.runtime.webhook import deliver_with_retry, upsert_dlq

logger = logging.getLogger(__name__)


def _backoff_seconds(attempts: int) -> int:
    return min(60, 2 ** max(1, attempts))


async def _poll_once(batch_size: int = 50) -> int:
    processed = 0
    async with SessionLocal() as db:
        rows = await db.execute(
            text(
                """
                SELECT id::text, subscription_id::text, endpoint_id::text, payload,
                       attempts, max_attempts, created_at
                FROM webhook_outbox
                WHERE status = 'PENDING'
                  AND next_retry_at <= NOW()
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT :batch_size
                """
            ),
            {"batch_size": batch_size},
        )
        items = rows.fetchall()

        for item in items:
            outbox_id, sub_id, endpoint_id, payload, attempts, max_attempts, created_at = item
            await db.execute(
                text(
                    """
                    UPDATE webhook_outbox
                    SET status = 'DELIVERING', updated_at = NOW()
                    WHERE id = CAST(:id AS uuid)
                    """
                ),
                {"id": outbox_id},
            )
            await db.commit()

            sub_row = await db.execute(
                text(
                    """
                    SELECT id::text, consumer_id, endpoint_id::text, target_url, active
                    FROM consumer_subscriptions
                    WHERE id = CAST(:id AS uuid)
                    """
                ),
                {"id": sub_id},
            )
            sub = sub_row.first()
            if sub is None:
                await db.execute(
                    text("UPDATE webhook_outbox SET status='FAILED', updated_at=NOW() WHERE id=CAST(:id AS uuid)"),
                    {"id": outbox_id},
                )
                await db.commit()
                processed += 1
                continue

            subscription = {
                "id": sub[0],
                "consumer_id": sub[1],
                "endpoint_id": sub[2],
                "target_url": sub[3],
                "active": sub[4],
            }

            event_id = payload.get("event_id") if isinstance(payload, dict) else None
            if not event_id:
                event_id = str(uuid.uuid4())

            ok = await deliver_with_retry(
                db,
                event_id=event_id,
                endpoint_id=endpoint_id,
                subscription=subscription,
                payload=payload if isinstance(payload, dict) else json.loads(payload),
                max_attempts=1,
                persist_dlq=False,
            )

            if ok:
                await db.execute(
                    text(
                        """
                        UPDATE webhook_outbox
                        SET status = 'DELIVERED', updated_at = NOW(), attempts = attempts + 1
                        WHERE id = CAST(:id AS uuid)
                        """
                    ),
                    {"id": outbox_id},
                )
                latency = (datetime.now(timezone.utc) - created_at).total_seconds()
                OUTBOX_DELIVERY_LATENCY_SECONDS.observe(max(0.0, latency))
                await db.commit()
            else:
                next_attempt = attempts + 1
                if next_attempt >= max_attempts:
                    await db.execute(
                        text(
                            """
                            UPDATE webhook_outbox
                            SET status = 'FAILED', attempts = :attempts, updated_at = NOW()
                            WHERE id = CAST(:id AS uuid)
                            """
                        ),
                        {"id": outbox_id, "attempts": next_attempt},
                    )
                    await upsert_dlq(
                        db,
                        event_id=str(event_id),
                        consumer_id=subscription["consumer_id"],
                        endpoint_id=endpoint_id,
                        target_url=subscription["target_url"],
                        payload={"event": payload, "failed_at": datetime.now(timezone.utc).isoformat()},
                        failure_reason="outbox max attempts exhausted",
                        attempt_count=next_attempt,
                    )
                    await db.commit()
                else:
                    retry_at = datetime.now(timezone.utc) + timedelta(seconds=_backoff_seconds(next_attempt))
                    await db.execute(
                        text(
                            """
                            UPDATE webhook_outbox
                            SET status = 'PENDING', attempts = :attempts, next_retry_at = :retry_at, updated_at = NOW()
                            WHERE id = CAST(:id AS uuid)
                            """
                        ),
                        {"id": outbox_id, "attempts": next_attempt, "retry_at": retry_at},
                    )
                    await db.commit()

            processed += 1

        pending = await db.execute(text("SELECT COUNT(*) FROM webhook_outbox WHERE status = 'PENDING'"))
        OUTBOX_PENDING_GAUGE.set(float(pending.scalar_one()))

    return processed


async def run_outbox_worker(stop_event: asyncio.Event, poll_interval_seconds: float = 0.25) -> None:
    logger.info("outbox worker started")
    while not stop_event.is_set():
        try:
            processed = await _poll_once()
            if processed == 0:
                await asyncio.sleep(poll_interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("outbox worker loop error")
            await asyncio.sleep(1.0)
    logger.info("outbox worker stopped")
