from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.runtime.events import build_default_publisher
from app.runtime.document_store import DocumentStore
from app.runtime.drift_event_dlq import (
    get_event_row,
    list_event_dlq,
    replay_event_dlq,
)
from app.runtime.webhook import (
    get_dlq_entry,
    list_delivery_attempts,
    list_dlq_entries,
    replay_dlq_entry,
)

router = APIRouter(prefix="/api/v1", tags=["reliability"])


def _document_store(request: Request) -> DocumentStore | None:
    return getattr(request.app.state, "document_store", None)


@router.get("/webhook-dlq")
async def webhook_dlq(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    return await list_dlq_entries(db, limit=limit)


@router.get("/webhook-dlq/{dlq_id}")
async def webhook_dlq_entry(dlq_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    entry = await get_dlq_entry(db, dlq_id)
    if entry is None:
        raise HTTPException(404, "dlq entry not found")
    return entry


@router.post("/webhook-dlq/{dlq_id}/replay")
async def replay_webhook_dlq(
    dlq_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await replay_dlq_entry(db, dlq_id=dlq_id, document_store=_document_store(request))
    if not result.get("replayed") and result.get("error") == "dlq_not_found":
        raise HTTPException(404, "dlq entry not found")
    return result


@router.get("/drift-event-dlq")
async def drift_event_dlq(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    return await list_event_dlq(db, limit=limit)


@router.get("/drift-event-dlq/{dlq_id}")
async def drift_event_dlq_entry(dlq_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    entry = await get_event_row(db, dlq_id)
    if entry is None:
        raise HTTPException(404, "drift event dlq entry not found")
    return entry


@router.post("/drift-event-dlq/{dlq_id}/replay")
async def replay_drift_event_dlq(
    dlq_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    publisher = getattr(request.app.state, "event_publisher", None) or build_default_publisher()
    result = await replay_event_dlq(
        db,
        dlq_id=dlq_id,
        publisher=publisher,
        document_store=_document_store(request),
    )
    if not result.get("replayed") and result.get("error") == "dlq_not_found":
        raise HTTPException(404, "drift event dlq entry not found")
    return result


@router.get("/webhook-delivery-attempts")
async def webhook_delivery_attempts(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    return await list_delivery_attempts(db, limit=limit)


@router.get("/documents/payload-snapshots")
async def payload_snapshots(request: Request, limit: int = Query(50, ge=1, le=200)) -> list[dict]:
    store = _document_store(request)
    if store is None:
        return []
    return await store.list_payload_snapshots(limit=limit)


@router.get("/documents/schema-diffs")
async def schema_diffs(request: Request, limit: int = Query(50, ge=1, le=200)) -> list[dict]:
    store = _document_store(request)
    if store is None:
        return []
    return await store.list_schema_diffs(limit=limit)


@router.get("/documents/validation-errors")
async def validation_errors(request: Request, limit: int = Query(50, ge=1, le=200)) -> list[dict]:
    store = _document_store(request)
    if store is None:
        return []
    return await store.list_validation_errors(limit=limit)


@router.get("/documents/replay-artifacts")
async def replay_artifacts(request: Request, limit: int = Query(50, ge=1, le=200)) -> list[dict]:
    store = _document_store(request)
    if store is None:
        return []
    return await store.list_replay_artifacts(limit=limit)
