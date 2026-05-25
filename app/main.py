from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.engine import (
    classify_contract_drift,
    get_active_baseline,
    log_drift_violations,
    register_payload_snapshot,
    structural_diff,
)
from app.core.parser import fingerprint_schema, normalize_types, structural_string
from app.db import close_db, get_db


class PayloadSubmission(BaseModel):
    service_name: str
    http_method: str
    route_path: str
    payload: dict[str, Any]


app = FastAPI(title="SchemaPilot Contract Guard", version="1.0.0")


@app.on_event("shutdown")
async def _shutdown() -> None:
    await close_db()


@app.post("/track")
async def track_payload(submission: PayloadSubmission, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    normalized = normalize_types(submission.payload)
    structural = structural_string(submission.payload)
    fingerprint = fingerprint_schema(submission.payload)

    endpoint_id, inserted = await register_payload_snapshot(
        db,
        service_name=submission.service_name,
        http_method=submission.http_method.upper(),
        route_path=submission.route_path,
        fingerprint=fingerprint,
        normalized_schema=normalized,
    )

    baseline = await get_active_baseline(db, endpoint_id)
    diff_count = 0
    severities: dict[str, int] = {"SAFE": 0, "RISKY": 0, "BREAKING": 0}

    if baseline is None and inserted:
        async with db.begin():
            await db.execute(
                text(
                    """
                    UPDATE schema_snapshots
                    SET is_active_baseline = FALSE
                    WHERE endpoint_id = :endpoint_id::uuid
                    """
                ),
                {"endpoint_id": endpoint_id},
            )
            await db.execute(
                text(
                    """
                    UPDATE schema_snapshots
                    SET is_active_baseline = TRUE
                    WHERE endpoint_id = :endpoint_id::uuid AND fingerprint = :fingerprint
                    """
                ),
                {"endpoint_id": endpoint_id, "fingerprint": fingerprint},
            )
        baseline = normalized

    if baseline is not None:
        diffs = structural_diff(baseline, normalized)
        classify_contract_drift(diffs)
        await log_drift_violations(
            db,
            endpoint_id=endpoint_id,
            fingerprint=fingerprint,
            diffs=diffs,
        )
        diff_count = len([d for d in diffs if d.get("severity")])
        for item in diffs:
            sev = item.get("severity")
            if sev in severities:
                severities[sev] += 1

    return {
        "endpoint_id": endpoint_id,
        "fingerprint": fingerprint,
        "inserted": inserted,
        "structural": structural,
        "diff_count": diff_count,
        "severities": severities,
    }
