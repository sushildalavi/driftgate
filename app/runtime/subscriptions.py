from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.runtime.models import severity_rank


async def create_subscription(
    db: AsyncSession,
    *,
    consumer_id: str,
    endpoint_id: str,
    target_url: str,
    severity_threshold: str,
    schema_version: int | None,
    active: bool,
) -> dict[str, Any]:
    row = await db.execute(
        text(
            """
            INSERT INTO consumer_subscriptions(
                consumer_id, endpoint_id, target_url, severity_threshold, schema_version, active
            )
            VALUES (
                :consumer_id, CAST(:endpoint_id AS uuid), :target_url, :severity_threshold,
                :schema_version, :active
            )
            RETURNING id::text, consumer_id, endpoint_id::text, target_url, severity_threshold,
                      schema_version, active, created_at, updated_at
            """
        ),
        {
            "consumer_id": consumer_id,
            "endpoint_id": endpoint_id,
            "target_url": target_url,
            "severity_threshold": severity_threshold,
            "schema_version": schema_version,
            "active": active,
        },
    )
    await db.commit()
    r = row.one()
    return {
        "id": r[0], "consumer_id": r[1], "endpoint_id": r[2], "target_url": r[3],
        "severity_threshold": r[4], "schema_version": r[5], "active": r[6],
        "created_at": r[7].isoformat(), "updated_at": r[8].isoformat(),
    }


async def list_subscriptions(db: AsyncSession, endpoint_id: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT id::text, consumer_id, endpoint_id::text, target_url, severity_threshold,
               schema_version, active, created_at, updated_at
        FROM consumer_subscriptions
    """
    params: dict[str, Any] = {}
    if endpoint_id:
        sql += " WHERE endpoint_id = CAST(:endpoint_id AS uuid)"
        params["endpoint_id"] = endpoint_id
    sql += " ORDER BY created_at DESC"
    rows = await db.execute(text(sql), params)
    out = []
    for r in rows.fetchall():
        out.append(
            {
                "id": r[0], "consumer_id": r[1], "endpoint_id": r[2], "target_url": r[3],
                "severity_threshold": r[4], "schema_version": r[5], "active": r[6],
                "created_at": r[7].isoformat(), "updated_at": r[8].isoformat(),
            }
        )
    return out


async def update_subscription(db: AsyncSession, subscription_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    mutable = {k: v for k, v in patch.items() if k in {"target_url", "severity_threshold", "schema_version", "active"}}
    if not mutable:
        return await get_subscription(db, subscription_id)
    set_expr = ", ".join(f"{k} = :{k}" for k in mutable)
    mutable["subscription_id"] = subscription_id
    await db.execute(
        text(
            f"""
            UPDATE consumer_subscriptions
            SET {set_expr}, updated_at = NOW()
            WHERE id = CAST(:subscription_id AS uuid)
            """
        ),
        mutable,
    )
    await db.commit()
    return await get_subscription(db, subscription_id)


async def get_subscription(db: AsyncSession, subscription_id: str) -> dict[str, Any] | None:
    row = await db.execute(
        text(
            """
            SELECT id::text, consumer_id, endpoint_id::text, target_url, severity_threshold,
                   schema_version, active, created_at, updated_at
            FROM consumer_subscriptions
            WHERE id = CAST(:subscription_id AS uuid)
            """
        ),
        {"subscription_id": subscription_id},
    )
    r = row.first()
    if r is None:
        return None
    return {
        "id": r[0], "consumer_id": r[1], "endpoint_id": r[2], "target_url": r[3],
        "severity_threshold": r[4], "schema_version": r[5], "active": r[6],
        "created_at": r[7].isoformat(), "updated_at": r[8].isoformat(),
    }


async def select_affected_subscriptions(
    db: AsyncSession,
    *,
    endpoint_id: str,
    new_version: int,
    severity: str,
) -> list[dict[str, Any]]:
    rows = await db.execute(
        text(
            """
            SELECT id::text, consumer_id, endpoint_id::text, target_url, severity_threshold,
                   schema_version, active
            FROM consumer_subscriptions
            WHERE endpoint_id = CAST(:endpoint_id AS uuid)
              AND active = TRUE
              AND (schema_version IS NULL OR schema_version <= :new_version)
            """
        ),
        {"endpoint_id": endpoint_id, "new_version": new_version},
    )
    out = []
    for r in rows.fetchall():
        if severity_rank(severity) >= severity_rank(r[4]):
            out.append(
                {
                    "id": r[0],
                    "consumer_id": r[1],
                    "endpoint_id": r[2],
                    "target_url": r[3],
                    "severity_threshold": r[4],
                    "schema_version": r[5],
                    "active": r[6],
                }
            )
    return out
