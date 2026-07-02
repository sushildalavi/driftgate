from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import SessionLocal
from app.runtime.document_store import DocumentStore
from app.runtime.metrics import DRIFT_EVENT_DLQ_SIZE
from app.runtime.models import DriftEvent


def _event_payload(event: DriftEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "endpoint_id": event.endpoint_id,
        "endpoint_name": event.endpoint_name,
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


async def record_event_failure(
    event: DriftEvent,
    *,
    failure_reason: str,
    publisher_name: str,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    factory = session_factory or SessionLocal
    async with factory() as db:
        inserted = await db.execute(
            text(
                """
                INSERT INTO drift_event_dlq(
                    event_id, endpoint_id, endpoint_name, namespace, payload,
                    failure_reason, publisher_name, attempt_count, status, last_failure_at
                )
                VALUES (
                    CAST(:event_id AS uuid), CAST(:endpoint_id AS uuid), :endpoint_name, :namespace,
                    CAST(:payload AS jsonb), :failure_reason, :publisher_name, 1, 'PENDING', NOW()
                )
                ON CONFLICT (event_id)
                DO UPDATE SET
                    failure_reason = EXCLUDED.failure_reason,
                    publisher_name = EXCLUDED.publisher_name,
                    attempt_count = drift_event_dlq.attempt_count + 1,
                    last_failure_at = NOW()
                RETURNING xmax = 0 AS inserted
                """
            ),
            {
                "event_id": event.event_id,
                "endpoint_id": event.endpoint_id,
                "endpoint_name": event.endpoint_name,
                "namespace": event.namespace,
                "payload": json.dumps(_event_payload(event)),
                "failure_reason": failure_reason,
                "publisher_name": publisher_name,
            },
        )
        row = inserted.first()
        if row is not None and bool(row[0]):
            DRIFT_EVENT_DLQ_SIZE.inc()
        await db.commit()


async def get_event_row(db: AsyncSession, dlq_id: str) -> dict[str, Any] | None:
    row = await db.execute(
        text(
            """
            SELECT id::text, event_id::text, endpoint_id::text, endpoint_name, namespace, payload,
                   failure_reason, publisher_name, attempt_count, status, created_at, updated_at,
                   last_failure_at, replayed_at, replay_error
            FROM drift_event_dlq
            WHERE id = CAST(:dlq_id AS uuid)
            """
        ),
        {"dlq_id": dlq_id},
    )
    item = row.first()
    if item is None:
        return None
    payload = item[5]
    return {
        "id": item[0],
        "event_id": item[1],
        "endpoint_id": item[2],
        "endpoint_name": item[3],
        "namespace": item[4],
        "payload": payload,
        "failure_reason": item[6],
        "publisher_name": item[7],
        "attempt_count": item[8],
        "status": item[9],
        "created_at": item[10].isoformat(),
        "updated_at": item[11].isoformat(),
        "last_failure_at": item[12].isoformat(),
        "replayed_at": item[13].isoformat() if item[13] is not None else None,
        "replay_error": item[14],
    }


async def list_event_dlq(db: AsyncSession, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = await db.execute(
        text(
            """
            SELECT id::text, event_id::text, endpoint_id::text, endpoint_name, namespace, payload,
                   failure_reason, publisher_name, attempt_count, status, created_at, updated_at,
                   last_failure_at, replayed_at, replay_error
            FROM drift_event_dlq
            ORDER BY last_failure_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    return [
        {
            "id": item[0],
            "event_id": item[1],
            "endpoint_id": item[2],
            "endpoint_name": item[3],
            "namespace": item[4],
            "payload": item[5],
            "failure_reason": item[6],
            "publisher_name": item[7],
            "attempt_count": item[8],
            "status": item[9],
            "created_at": item[10].isoformat(),
            "updated_at": item[11].isoformat(),
            "last_failure_at": item[12].isoformat(),
            "replayed_at": item[13].isoformat() if item[13] is not None else None,
            "replay_error": item[14],
        }
        for item in rows.fetchall()
    ]


async def replay_event_dlq(
    db: AsyncSession,
    *,
    dlq_id: str,
    publisher: Any,
    document_store: DocumentStore | None = None,
) -> dict[str, Any]:
    row = await get_event_row(db, dlq_id)
    if row is None:
        return {"replayed": False, "error": "dlq_not_found"}
    if row["status"] == "REPLAYED":
        return {"replayed": True, "dlq": row, "already_replayed": True}

    payload = row["payload"] if isinstance(row["payload"], dict) else {}
    event = DriftEvent(
        event_id=str(payload.get("event_id", row["event_id"])),
        endpoint_id=str(payload.get("endpoint_id", row["endpoint_id"])),
        endpoint_name=str(payload.get("endpoint_name", row["endpoint_name"])),
        namespace=str(payload.get("namespace", row["namespace"])),
        old_fingerprint=str(payload.get("old_fingerprint", "")),
        new_fingerprint=str(payload.get("new_fingerprint", "")),
        old_version=int(payload.get("old_version", 0)),
        new_version=int(payload.get("new_version", 0)),
        severity=str(payload.get("severity", "SAFE")),
        compatibility_classification=str(payload.get("compatibility_classification", "SAFE")),
        timestamp=str(payload.get("timestamp", datetime.now(timezone.utc).isoformat())),
        schema_diff_summary=list(payload.get("schema_diff_summary", [])),
        affected_consumer_count=int(payload.get("affected_consumer_count", 0)),
    )

    replay_error: str | None = None
    try:
        await publisher.publish_drift_detected(event)
        await db.execute(
            text(
                """
                UPDATE drift_event_dlq
                SET status = 'REPLAYED',
                    replayed_at = NOW(),
                    replay_error = NULL,
                    updated_at = NOW()
                WHERE id = CAST(:dlq_id AS uuid)
                """
            ),
            {"dlq_id": dlq_id},
        )
        await db.commit()
    except Exception as exc:
        replay_error = f"{type(exc).__name__}: {exc}"
        await db.execute(
            text(
                """
                UPDATE drift_event_dlq
                SET status = 'PENDING',
                    attempt_count = attempt_count + 1,
                    replay_error = :replay_error,
                    last_failure_at = NOW(),
                    updated_at = NOW()
                WHERE id = CAST(:dlq_id AS uuid)
                """
            ),
            {"dlq_id": dlq_id, "replay_error": replay_error},
        )
        await db.commit()

    updated = await get_event_row(db, dlq_id)
    if updated is not None and updated["status"] == "REPLAYED":
        DRIFT_EVENT_DLQ_SIZE.dec()
    if document_store is not None and updated is not None:
        await document_store.store_replay_artifact(
            source="runtime-drift-event-dlq",
            artifact_type="drift_event_replay",
            payload={
                "dlq_id": dlq_id,
                "event_id": updated["event_id"],
                "endpoint_id": updated["endpoint_id"],
                "endpoint_name": updated["endpoint_name"],
                "replayed": updated["status"] == "REPLAYED",
                "replay_error": replay_error,
            },
            metadata={"publisher": getattr(publisher, "provider_name", publisher.__class__.__name__)},
        )

    if replay_error is not None:
        return {"replayed": False, "error": replay_error, "dlq": updated}
    return {"replayed": True, "dlq": updated}


def serialize_event(event: DriftEvent) -> dict[str, Any]:
    return _event_payload(event)
