from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.deps import DbSession, require_admin
from app.models import Changelog, SchemaDiff, SchemaSnapshot
from app.schemas import ChangelogGenerateRequest, ChangelogOut

router = APIRouter(tags=["changelog"])


@router.get("/api/endpoints/{endpoint_id}/changelogs", response_model=list[ChangelogOut])
async def list_changelogs_for_endpoint(
    endpoint_id: uuid.UUID,
    db: DbSession,
    limit: int = Query(20, ge=1, le=100),
) -> list[ChangelogOut]:
    r = await db.execute(
        select(Changelog)
        .where(Changelog.endpoint_id == endpoint_id)
        .order_by(Changelog.created_at.desc())
        .limit(limit)
    )
    return [ChangelogOut.model_validate(c) for c in r.scalars().all()]


@router.get("/api/changelogs/{changelog_id}", response_model=ChangelogOut)
async def get_changelog(changelog_id: uuid.UUID, db: DbSession) -> ChangelogOut:
    c = await db.get(Changelog, changelog_id)
    if not c:
        raise HTTPException(404, "changelog not found")
    return ChangelogOut.model_validate(c)


@router.post(
    "/api/changelogs/generate",
    response_model=ChangelogOut,
    dependencies=[Depends(require_admin)],
)
async def generate_changelog(
    req: ChangelogGenerateRequest, db: DbSession
) -> ChangelogOut:
    from app.core.changelog import generate_changelog as _generate

    snapshot = await db.get(SchemaSnapshot, req.snapshot_id)
    if not snapshot:
        raise HTTPException(404, "snapshot not found")
    if not snapshot.normalized_schema_json:
        raise HTTPException(422, "snapshot has no schema (fetch failed)")

    # Fetch diffs for this snapshot
    r = await db.execute(
        select(SchemaDiff).where(SchemaDiff.new_snapshot_id == snapshot.id)
    )
    diffs_rows = r.scalars().all()
    if not diffs_rows:
        raise HTTPException(422, "no diffs found for snapshot")

    result = await _generate(db, snapshot, diffs_rows)
    return ChangelogOut.model_validate(result)
