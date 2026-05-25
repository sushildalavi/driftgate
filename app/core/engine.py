from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_endpoint(
    db: AsyncSession,
    *,
    service_name: str,
    http_method: str,
    route_path: str,
) -> str:
    existing = await db.execute(
        text(
            """
            SELECT id::text FROM api_endpoints
            WHERE service_name = :service_name
              AND http_method = :http_method
              AND route_path = :route_path
            """
        ),
        {
            "service_name": service_name,
            "http_method": http_method,
            "route_path": route_path,
        },
    )
    endpoint_id = existing.scalar_one_or_none()
    if endpoint_id:
        return endpoint_id

    inserted = await db.execute(
        text(
            """
            INSERT INTO api_endpoints(service_name, http_method, route_path)
            VALUES (:service_name, :http_method, :route_path)
            RETURNING id::text
            """
        ),
        {
            "service_name": service_name,
            "http_method": http_method,
            "route_path": route_path,
        },
    )
    return inserted.scalar_one()


async def register_snapshot(
    db: AsyncSession,
    *,
    endpoint_id: str,
    fingerprint: str,
    normalized_schema: Any,
) -> bool:
    existing = await db.execute(
        text("SELECT fingerprint FROM schema_snapshots WHERE fingerprint = :fingerprint"),
        {"fingerprint": fingerprint},
    )
    if existing.scalar_one_or_none():
        return False

    await db.execute(
        text(
            """
            INSERT INTO schema_snapshots(fingerprint, endpoint_id, normalized_schema)
            VALUES (:fingerprint, :endpoint_id::uuid, CAST(:normalized_schema AS jsonb))
            """
        ),
        {
            "fingerprint": fingerprint,
            "endpoint_id": endpoint_id,
            "normalized_schema": normalized_schema,
        },
    )
    return True
