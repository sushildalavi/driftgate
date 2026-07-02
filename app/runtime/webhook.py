from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.runtime.document_store import DocumentStore
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
    inserted = await db.execute(
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
            RETURNING xmax = 0 AS inserted
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
    row = inserted.first()
    if row is not None and bool(row[0]):
        DLQ_SIZE.inc()
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


async def list_dlq_entries(db: AsyncSession, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = await db.execute(
        text(
            """
            SELECT id::text, event_id::text, consumer_id, endpoint_id::text, target_url,
                   payload, failure_reason, attempt_count, created_at, last_attempt_at
            FROM webhook_delivery_dlq
            ORDER BY last_attempt_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    out: list[dict[str, Any]] = []
    for row in rows.fetchall():
        out.append(
            {
                "id": row[0],
                "event_id": row[1],
                "consumer_id": row[2],
                "endpoint_id": row[3],
                "target_url": row[4],
                "payload": row[5],
                "failure_reason": row[6],
                "attempt_count": row[7],
                "created_at": row[8].isoformat(),
                "last_attempt_at": row[9].isoformat(),
            }
        )
    return out


async def get_dlq_entry(db: AsyncSession, dlq_id: str) -> dict[str, Any] | None:
    row = await db.execute(
        text(
            """
            SELECT id::text, event_id::text, consumer_id, endpoint_id::text, target_url,
                   payload, failure_reason, attempt_count, created_at, last_attempt_at
            FROM webhook_delivery_dlq
            WHERE id = CAST(:dlq_id AS uuid)
            """
        ),
        {"dlq_id": dlq_id},
    )
    entry = row.first()
    if entry is None:
        return None
    return {
        "id": entry[0],
        "event_id": entry[1],
        "consumer_id": entry[2],
        "endpoint_id": entry[3],
        "target_url": entry[4],
        "payload": entry[5],
        "failure_reason": entry[6],
        "attempt_count": entry[7],
        "created_at": entry[8].isoformat(),
        "last_attempt_at": entry[9].isoformat(),
    }


async def list_delivery_attempts(db: AsyncSession, *, limit: int = 100) -> list[dict[str, Any]]:
    rows = await db.execute(
        text(
            """
            SELECT id::text, event_id::text, consumer_id, endpoint_id::text, target_url,
                   success, failure_reason, attempt_count, attempted_at
            FROM webhook_delivery_attempts
            ORDER BY attempted_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    out: list[dict[str, Any]] = []
    for row in rows.fetchall():
        out.append(
            {
                "id": row[0],
                "event_id": row[1],
                "consumer_id": row[2],
                "endpoint_id": row[3],
                "target_url": row[4],
                "success": row[5],
                "failure_reason": row[6],
                "attempt_count": row[7],
                "attempted_at": row[8].isoformat(),
            }
        )
    return out


async def replay_dlq_entry(
    db: AsyncSession,
    *,
    dlq_id: str,
    document_store: DocumentStore | None = None,
) -> dict[str, Any]:
    entry = await get_dlq_entry(db, dlq_id)
    if entry is None:
        return {"replayed": False, "error": "dlq_not_found"}

    sub_row = await db.execute(
        text(
            """
            SELECT id::text, consumer_id, endpoint_id::text, target_url, active
            FROM consumer_subscriptions
            WHERE endpoint_id = CAST(:endpoint_id AS uuid)
              AND consumer_id = :consumer_id
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"endpoint_id": entry["endpoint_id"], "consumer_id": entry["consumer_id"]},
    )
    sub = sub_row.first()
    if sub is None:
        return {"replayed": False, "error": "subscription_not_found", "dlq": entry}

    subscription = {
        "id": sub[0],
        "consumer_id": sub[1],
        "endpoint_id": sub[2],
        "target_url": sub[3],
        "active": sub[4],
    }
    payload = entry["payload"]
    event_payload = payload.get("event") if isinstance(payload, dict) else payload
    event_id = entry["event_id"]

    ok = await deliver_with_retry(
        db,
        event_id=event_id,
        endpoint_id=entry["endpoint_id"],
        subscription=subscription,
        payload=event_payload if isinstance(event_payload, dict) else {"value": event_payload},
        max_attempts=1,
        persist_dlq=False,
    )

    artifact = {
        "dlq_id": dlq_id,
        "event_id": event_id,
        "consumer_id": entry["consumer_id"],
        "endpoint_id": entry["endpoint_id"],
        "target_url": entry["target_url"],
        "replayed": ok,
        "failure_reason": None if ok else entry["failure_reason"],
        "replayed_at": datetime.now(timezone.utc).isoformat(),
    }

    if document_store is not None:
        await document_store.store_replay_artifact(
            source="runtime-dlq",
            artifact_type="dlq_replay",
            payload=artifact,
            metadata={"dlq_id": dlq_id, "consumer_id": entry["consumer_id"]},
        )

    return artifact
