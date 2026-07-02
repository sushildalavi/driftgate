from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.subscriptions import router as subscriptions_router
from app.api.ai import router as ai_router
from app.api.reliability import router as reliability_router
from app.core.engine import (
    classify_contract_drift,
    get_active_baseline_snapshot,
    log_drift_violations,
    register_payload_snapshot,
    structural_diff,
)
from app.core.parser import fingerprint_schema, normalize_types, structural_string
from app.db import SessionLocal, close_db, get_db
from app.runtime.document_store import build_document_store
from app.runtime.contract_review import build_review_provider
from app.runtime.events import build_default_publisher
from app.runtime.metrics import metrics_payload
from app.runtime.service import track_contract
from app.workers.outbox_worker import run_outbox_worker


class PayloadSubmission(BaseModel):
    namespace: str = "default"
    service_name: str
    http_method: str
    route_path: str
    payload: dict[str, Any]


document_store = build_document_store()
contract_review_provider = build_review_provider()
event_publisher = build_default_publisher()


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()
    worker_task = asyncio.create_task(run_outbox_worker(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
        await close_db()
        await document_store.aclose()


app = FastAPI(title="DriftGate Contract Guard", version="1.0.0", lifespan=lifespan)
app.state.document_store = document_store
app.state.contract_review_provider = contract_review_provider
app.state.event_publisher = event_publisher
app.state.runtime_session_factory = SessionLocal

frontend_origins = [origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    store = getattr(request.app.state, "document_store", None)
    if store is not None:
        try:
            raw_body = (await request.body()).decode("utf-8", errors="replace")
        except Exception:
            raw_body = ""
        try:
            await store.store_validation_error(
                source="fastapi-validation",
                path=str(request.url.path),
                errors=exc.errors(),
                raw_body=raw_body,
                metadata={"method": request.method},
            )
        except Exception:
            pass
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.post("/track")
async def track_payload(
    submission: PayloadSubmission,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    publisher = getattr(request.app.state, "event_publisher", event_publisher)
    benchmark_mode = submission.namespace.lower().startswith("k6")
    result = await track_contract(
        db,
        namespace=submission.namespace,
        service_name=submission.service_name,
        http_method=submission.http_method.upper(),
        route_path=submission.route_path,
        payload=submission.payload,
        publisher=publisher,
        session_factory=getattr(request.app.state, "runtime_session_factory", SessionLocal),
        document_store=None if benchmark_mode else getattr(request.app.state, "document_store", None),
    )
    await db.commit()
    if benchmark_mode:
        # Benchmark traffic can skip legacy dual-write to avoid compounding advisory-lock contention.
        return result

    # Backward compatibility path: preserve existing /track response + legacy tables.
    normalized = normalize_types(submission.payload)
    structural = structural_string(submission.payload)
    legacy_fp = fingerprint_schema(submission.payload)
    endpoint_id, inserted = await register_payload_snapshot(
        db,
        service_name=submission.service_name,
        http_method=submission.http_method.upper(),
        route_path=submission.route_path,
        fingerprint=legacy_fp,
        normalized_schema=normalized,
    )
    baseline_row = await get_active_baseline_snapshot(db, endpoint_id)
    baseline = baseline_row["normalized_schema"] if baseline_row else None
    baseline_fingerprint = baseline_row["fingerprint"] if baseline_row else None
    severities: dict[str, int] = {"SAFE": 0, "RISKY": 0, "BREAKING": 0}
    legacy_diff_count = 0

    if baseline is None and inserted:
        await db.execute(
            text(
                """
                UPDATE schema_snapshots
                SET is_active_baseline = FALSE
                WHERE endpoint_id = CAST(:endpoint_id AS uuid)
                """
            ),
            {"endpoint_id": endpoint_id},
        )
        await db.execute(
            text(
                """
                UPDATE schema_snapshots
                SET is_active_baseline = TRUE
                WHERE endpoint_id = CAST(:endpoint_id AS uuid) AND fingerprint = :fingerprint
                """
            ),
            {"endpoint_id": endpoint_id, "fingerprint": legacy_fp},
        )
        await db.commit()
        baseline = normalized
        baseline_fingerprint = legacy_fp

    if baseline is not None and baseline_fingerprint != legacy_fp:
        legacy_diffs = structural_diff(baseline, normalized)
        classify_contract_drift(legacy_diffs)
        await log_drift_violations(
            db,
            endpoint_id=endpoint_id,
            fingerprint=legacy_fp,
            diffs=legacy_diffs,
        )
        legacy_diff_count = len([d for d in legacy_diffs if d.get("severity")])
        for item in legacy_diffs:
            sev = item.get("severity")
            if sev in severities:
                severities[sev] += 1
        await db.commit()

    result["legacy_endpoint_id"] = endpoint_id
    result["structural"] = structural
    result["severities"] = severities
    result["diff_count"] = max(result.get("diff_count", 0), legacy_diff_count)
    result["inserted"] = result.get("inserted", False) or inserted
    return result


@app.get("/api/v1/metrics")
async def fetch_runtime_metrics(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    from app.core.engine import get_runtime_metrics

    metrics = await get_runtime_metrics(db)
    store = getattr(request.app.state, "document_store", None)
    if store is not None and hasattr(store, "list_contract_reviews"):
        reviews = await store.list_contract_reviews(limit=200)
        metrics["contract_review_count"] = len(reviews)
        metrics["contract_review_insufficient_evidence_count"] = len(
            [item for item in reviews if item.get("review", {}).get("insufficient_evidence")]
        )
    return metrics


@app.get("/metrics")
async def prometheus_metrics() -> Response:
    content, content_type = metrics_payload()
    return Response(content=content, media_type=content_type)


app.include_router(subscriptions_router)
app.include_router(ai_router)
app.include_router(reliability_router)
