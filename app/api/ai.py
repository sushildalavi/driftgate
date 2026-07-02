from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.runtime.contract_review import (
    ContractReviewRequest,
    ContractReviewService,
    build_contract_review_service,
)
from app.runtime.document_store import DocumentStore

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


def _document_store(request: Request) -> DocumentStore | None:
    return getattr(request.app.state, "document_store", None)


def _review_service(request: Request) -> ContractReviewService:
    service = getattr(request.app.state, "contract_review_service", None)
    if service is None:
        provider = getattr(request.app.state, "contract_review_provider", None)
        service = build_contract_review_service(provider=provider)
        request.app.state.contract_review_service = service
    return service


@router.post("/contract-review")
async def contract_review(
    request: Request,
    body: ContractReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        record = await _review_service(request).review(
            db,
            document_store=_document_store(request),
            request=body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return record.model_dump()


@router.get("/contract-reviews")
async def contract_review_history(
    request: Request,
    endpoint_id: str | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> list[dict[str, Any]]:
    return await _review_service(request).history(
        _document_store(request),
        endpoint_id=endpoint_id,
        limit=limit,
    )
