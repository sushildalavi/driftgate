from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.runtime.canonical import canonicalize, fingerprint
from app.runtime.classifier import diff_and_classify, summarize_classification
from app.runtime.document_store import DocumentStore
from app.runtime.events import EventPublisher, publish_fire_and_forget
from app.runtime.metrics import (
    COMPATIBILITY_CLASSIFICATION_TOTAL,
    DRIFT_COUNT_TOTAL,
    DRIFT_DETECTION_LATENCY_SECONDS,
    OUTBOX_PENDING_GAUGE,
)
from app.runtime.models import DriftEvent
from app.runtime.registry import upsert_schema_version
from app.runtime.subscriptions import select_affected_subscriptions
from app.runtime.webhook import deliver_with_retry


logger = logging.getLogger(__name__)


async def _persist_document(task: str, awaitable: Any) -> None:
    try:
        await awaitable
    except Exception:
        logger.exception("failed to persist %s document", task)


async def _enqueue_webhook_outbox(
    db: AsyncSession,
    *,
    endpoint_id: str,
    event_id: str,
    classification: str,
    new_version: int,
    diffs: list[dict[str, Any]],
) -> int:
    affected = await select_affected_subscriptions(
        db,
        endpoint_id=endpoint_id,
        new_version=new_version,
        severity=classification,
    )

    inline_delivery = os.getenv("INLINE_WEBHOOK_DELIVERY", "true").lower() == "true"

    for sub in affected:
        outbox_row = await db.execute(
            text(
                """
                INSERT INTO webhook_outbox(subscription_id, endpoint_id, payload, status, attempts, max_attempts, next_retry_at)
                VALUES (
                    CAST(:subscription_id AS uuid),
                    CAST(:endpoint_id AS uuid),
                    CAST(:payload AS jsonb),
                    'PENDING',
                    0,
                    5,
                    NOW()
                )
                RETURNING id::text
                """
            ),
            {
                "subscription_id": sub["id"],
                "endpoint_id": endpoint_id,
                    "payload": json.dumps({
                        "event_id": event_id,
                        "endpoint_id": endpoint_id,
                        "classification": classification,
                        "new_version": new_version,
                    "diffs": diffs,
                    }),
                },
            )
        outbox_id = outbox_row.scalar_one()

        if inline_delivery:
            ok = await deliver_with_retry(
                db,
                event_id=event_id,
                endpoint_id=endpoint_id,
                subscription=sub,
                payload={
                    "event_id": event_id,
                    "endpoint_id": endpoint_id,
                    "classification": classification,
                    "new_version": new_version,
                    "diffs": diffs,
                },
                max_attempts=1,
                persist_dlq=True,
            )
            if ok:
                await db.execute(
                    text(
                        """
                        UPDATE webhook_outbox
                        SET status = 'DELIVERED', attempts = attempts + 1, updated_at = NOW()
                        WHERE id = CAST(:id AS uuid)
                        """
                    ),
                    {"id": outbox_id},
                )
            else:
                await db.execute(
                    text(
                        """
                        UPDATE webhook_outbox
                        SET status = 'FAILED', attempts = attempts + 1, updated_at = NOW()
                        WHERE id = CAST(:id AS uuid)
                        """
                    ),
                    {"id": outbox_id},
                )

    pending = await db.execute(text("SELECT COUNT(*) FROM webhook_outbox WHERE status = 'PENDING'"))
    OUTBOX_PENDING_GAUGE.set(float(pending.scalar_one()))
    return len(affected)


async def track_contract(
    db: AsyncSession,
    *,
    namespace: str,
    service_name: str,
    http_method: str,
    route_path: str,
    payload: dict[str, Any],
    publisher: EventPublisher,
    document_store: DocumentStore | None = None,
) -> dict[str, Any]:
    start = time.perf_counter()
    canonical_schema = canonicalize(payload)
    new_fingerprint = fingerprint(canonical_schema)

    endpoint_id, endpoint_name, new_record, inserted = await upsert_schema_version(
        db,
        namespace=namespace,
        service_name=service_name,
        http_method=http_method,
        route_path=route_path,
        fingerprint=new_fingerprint,
        canonical_schema=canonical_schema,
        classification="SAFE",
    )

    if document_store is not None:
        await _persist_document(
            "payload snapshot",
            document_store.store_payload_snapshot(
                endpoint_id=endpoint_id,
                namespace=namespace,
                service_name=service_name,
                http_method=http_method,
                route_path=route_path,
                payload=payload,
                fingerprint=new_fingerprint,
                classification="SAFE",
                source="runtime-track",
                metadata={
                    "route_path": route_path,
                    "service_name": service_name,
                },
            ),
        )

    diffs: list[dict[str, Any]] = []
    classification = "SAFE"
    old_fp = new_fingerprint
    old_version = new_record.version
    affected_count = 0

    if inserted and new_record.previous_version_id:
        prior = await db.execute(
            text(
                """
                SELECT version, fingerprint, canonical_schema
                FROM contract_schema_versions
                WHERE id = CAST(:id AS uuid)
                """
            ),
            {"id": new_record.previous_version_id},
        )
        p = prior.one()
        old_version = int(p[0])
        old_fp = str(p[1])
        diff_objs = diff_and_classify(p[2], canonical_schema)
        diffs = [d.__dict__ for d in diff_objs]
        classification = summarize_classification(diff_objs)

        if document_store is not None:
            await _persist_document(
                "schema diff",
                document_store.store_schema_diff(
                    endpoint_id=endpoint_id,
                    endpoint_name=endpoint_name,
                    namespace=namespace,
                    service_name=service_name,
                    http_method=http_method,
                    route_path=route_path,
                    old_fingerprint=old_fp,
                    new_fingerprint=new_fingerprint,
                    old_version=old_version,
                    new_version=new_record.version,
                    classification=classification,
                    diffs=diffs,
                    source="runtime-track",
                ),
            )

        await db.execute(
            text(
                """
                UPDATE contract_schema_versions
                SET compatibility_classification = :classification
                WHERE id = CAST(:id AS uuid)
                """
            ),
            {"classification": classification, "id": new_record.id},
        )

        event_id = str(uuid.uuid4())
        affected_count = await _enqueue_webhook_outbox(
            db,
            endpoint_id=endpoint_id,
            event_id=event_id,
            classification=classification,
            new_version=new_record.version,
            diffs=diffs,
        )

        COMPATIBILITY_CLASSIFICATION_TOTAL.labels(classification=classification).inc()
        DRIFT_COUNT_TOTAL.labels(severity=classification, endpoint_id=endpoint_id).inc()

        event = DriftEvent(
            event_id=event_id,
            endpoint_id=endpoint_id,
            endpoint_name=endpoint_name,
            namespace=namespace,
            old_fingerprint=old_fp,
            new_fingerprint=new_fingerprint,
            old_version=old_version,
            new_version=new_record.version,
            severity=classification,
            compatibility_classification=classification,
            timestamp=datetime.now(timezone.utc).isoformat(),
            schema_diff_summary=diffs,
            affected_consumer_count=affected_count,
        )
        publish_fire_and_forget(publisher, event)

    elapsed = time.perf_counter() - start
    DRIFT_DETECTION_LATENCY_SECONDS.observe(elapsed)

    return {
        "endpoint_id": endpoint_id,
        "endpoint_name": endpoint_name,
        "namespace": namespace,
        "schema_version": new_record.version,
        "fingerprint": new_fingerprint,
        "inserted": inserted,
        "compatibility_classification": classification,
        "diff_count": len(diffs),
        "affected_consumer_count": affected_count,
        "deliveries": [],
        "latency_seconds": elapsed,
    }
