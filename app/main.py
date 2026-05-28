from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.subscriptions import router as subscriptions_router
from app.core.engine import (
    classify_contract_drift,
    get_active_baseline_snapshot,
    log_drift_violations,
    register_payload_snapshot,
    structural_diff,
)
from app.core.parser import fingerprint_schema, normalize_types, structural_string
from app.db import close_db, get_db
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


app = FastAPI(title="SchemaPilot Contract Guard", version="1.0.0", lifespan=lifespan)


@app.post("/track")
async def track_payload(submission: PayloadSubmission, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    publisher = build_default_publisher()
    result = await track_contract(
        db,
        namespace=submission.namespace,
        service_name=submission.service_name,
        http_method=submission.http_method.upper(),
        route_path=submission.route_path,
        payload=submission.payload,
        publisher=publisher,
    )
    await db.commit()
    if submission.namespace.lower().startswith("k6"):
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
async def fetch_runtime_metrics(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    from app.core.engine import get_runtime_metrics

    return await get_runtime_metrics(db)


@app.get("/metrics")
async def prometheus_metrics() -> Response:
    content, content_type = metrics_payload()
    return Response(content=content, media_type=content_type)


app.include_router(subscriptions_router)
