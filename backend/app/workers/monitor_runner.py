from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.canonical import stable_schema_hash
from app.core.fetcher import FetchResult, fetch_endpoint
from app.core.locking import advisory_lock
from app.core.normalizer import normalize
from app.core.registry_loader import upsert_endpoints
from app.core.schema_diff import diff_schemas
from app.core.schema_infer import infer_schema
from app.models import ApiEndpoint, MonitorRun, SchemaDiff, SchemaSnapshot

log = logging.getLogger("driftgate.monitor")

LOCK_NAME = "driftgate.monitor"


@dataclass
class _EndpointResult:
    endpoint_id: uuid.UUID
    name: str
    snapshot_created: bool = False
    diffs_detected: int = 0
    error: str | None = None


async def run_monitor(session: AsyncSession, registry_path: str | None = None) -> uuid.UUID:
    """Main entry point. Returns monitor_run_id. Raises HTTPException(409) if already running."""
    from fastapi import HTTPException

    path = registry_path or settings.registry_path

    async with advisory_lock(session, LOCK_NAME) as got_lock:
        if not got_lock:
            # Find in-flight run id for the 409 response body
            r = await session.execute(
                select(MonitorRun)
                .where(MonitorRun.status == "running")
                .order_by(MonitorRun.started_at.desc())
                .limit(1)
            )
            running = r.scalar_one_or_none()
            raise HTTPException(
                409,
                detail={
                    "message": "monitor already running",
                    "monitor_run_id": str(running.id) if running else None,
                },
            )

        run = MonitorRun(status="running")
        session.add(run)
        await session.flush()
        run_id = run.id
        log.info("monitor run %s started", run_id)

        try:
            endpoints = await upsert_endpoints(session, path)
            results = await asyncio.gather(
                *[_process_endpoint(session, ep, run_id) for ep in endpoints],
                return_exceptions=True,
            )

            ok_results = [r for r in results if isinstance(r, _EndpointResult)]
            err_results = [r for r in results if isinstance(r, Exception)]

            snapshots = sum(r.snapshot_created for r in ok_results)
            diffs = sum(r.diffs_detected for r in ok_results)
            status = "partial_failure" if (err_results or any(r.error for r in ok_results)) else "success"

            await _retention_sweep(session)

            await session.execute(
                update(MonitorRun)
                .where(MonitorRun.id == run_id)
                .values(
                    finished_at=datetime.now(timezone.utc),
                    status=status,
                    endpoints_checked=len(endpoints),
                    snapshots_created=snapshots,
                    diffs_detected=diffs,
                )
            )
            await session.commit()
            log.info("monitor run %s finished: %s (snaps=%d diffs=%d)", run_id, status, snapshots, diffs)

        except Exception as exc:
            log.error("monitor run %s failed: %s", run_id, exc, exc_info=True)
            await session.rollback()
            async with session.begin():
                await session.execute(
                    update(MonitorRun)
                    .where(MonitorRun.id == run_id)
                    .values(
                        finished_at=datetime.now(timezone.utc),
                        status="failed",
                        error_message=str(exc),
                    )
                )
            raise

        return run_id


async def _process_endpoint(
    session: AsyncSession,
    endpoint: ApiEndpoint,
    run_id: uuid.UUID,
) -> _EndpointResult:
    result = _EndpointResult(endpoint_id=endpoint.id, name=endpoint.name)

    fetch: FetchResult = await fetch_endpoint(
        url=endpoint.url,
        method=endpoint.method,
        headers=endpoint.headers_json or {},
    )

    if not fetch.ok:
        sentinel_hash = f"FETCH_ERROR:{fetch.error}"
        snap = SchemaSnapshot(
            endpoint_id=endpoint.id,
            monitor_run_id=run_id,
            schema_hash=sentinel_hash,
            status_code=fetch.status_code,
            response_time_ms=fetch.response_time_ms,
            response_size_bytes=fetch.response_size_bytes,
            normalized_schema_json=None,
            raw_sample_json=None,
            fetch_error=fetch.error,
        )
        session.add(snap)
        await session.flush()
        result.snapshot_created = True
        result.error = fetch.error
        log.warning("endpoint %s fetch failed: %s", endpoint.name, fetch.error)
        return result

    normalized_body = normalize(fetch.body)
    nodes = infer_schema(normalized_body)
    schema_hash = stable_schema_hash(nodes)
    schema_json = [n.model_dump() for n in nodes]

    snap = SchemaSnapshot(
        endpoint_id=endpoint.id,
        monitor_run_id=run_id,
        schema_hash=schema_hash,
        status_code=fetch.status_code,
        response_time_ms=fetch.response_time_ms,
        response_size_bytes=fetch.response_size_bytes,
        normalized_schema_json=schema_json,
        raw_sample_json=normalized_body,
        fetch_error=None,
    )
    session.add(snap)
    await session.flush()
    result.snapshot_created = True

    prior = await _get_prior_snapshot(session, endpoint.id, snap.id)
    if prior and prior.schema_hash != schema_hash and not prior.schema_hash.startswith("FETCH_ERROR:"):
        from app.core.schema_infer import SchemaNode

        old_nodes = [SchemaNode(**n) for n in (prior.normalized_schema_json or [])]
        diffs = diff_schemas(old_nodes, nodes)
        for d in diffs:
            session.add(
                SchemaDiff(
                    endpoint_id=endpoint.id,
                    old_snapshot_id=prior.id,
                    new_snapshot_id=snap.id,
                    severity=d.severity,
                    change_type=d.change_type,
                    path=d.path,
                    old_type=d.old_type,
                    new_type=d.new_type,
                    old_value_json=d.old_value,
                    new_value_json=d.new_value,
                    message=d.message,
                )
            )
        result.diffs_detected = len(diffs)
        if diffs:
            log.info("endpoint %s: %d diffs detected", endpoint.name, len(diffs))

    await session.flush()
    return result


async def _get_prior_snapshot(
    session: AsyncSession, endpoint_id: uuid.UUID, current_id: uuid.UUID
) -> SchemaSnapshot | None:
    r = await session.execute(
        select(SchemaSnapshot)
        .where(
            SchemaSnapshot.endpoint_id == endpoint_id,
            SchemaSnapshot.id != current_id,
            SchemaSnapshot.normalized_schema_json.isnot(None),
        )
        .order_by(SchemaSnapshot.created_at.desc())
        .limit(1)
    )
    return r.scalar_one_or_none()


async def _retention_sweep(session: AsyncSession) -> None:
    """NULL out raw_sample_json for all snapshots beyond the 10 most recent per endpoint."""
    keep = settings.raw_retention_per_endpoint
    r = await session.execute(select(ApiEndpoint.id))
    endpoint_ids = r.scalars().all()

    for ep_id in endpoint_ids:
        r2 = await session.execute(
            select(SchemaSnapshot.id)
            .where(SchemaSnapshot.endpoint_id == ep_id)
            .order_by(SchemaSnapshot.created_at.desc())
            .limit(keep)
        )
        keep_ids = r2.scalars().all()
        if not keep_ids:
            continue
        await session.execute(
            update(SchemaSnapshot)
            .where(
                SchemaSnapshot.endpoint_id == ep_id,
                SchemaSnapshot.id.not_in(keep_ids),
                SchemaSnapshot.raw_sample_json.isnot(None),
            )
            .values(raw_sample_json=None)
        )
