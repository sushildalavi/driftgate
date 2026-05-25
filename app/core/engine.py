from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def route_lock_id(route_path: str) -> int:
    digest = hashlib.sha256(route_path.encode("utf-8")).hexdigest()
    return int(digest[:15], 16)


def _flatten_schema(schema: Any, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(schema, dict):
        for key, value in schema.items():
            path = f"{prefix}.{key}" if prefix else key
            out.update(_flatten_schema(value, path))
        return out
    if isinstance(schema, list):
        out[prefix] = "array"
        for i, value in enumerate(schema):
            out.update(_flatten_schema(value, f"{prefix}[*{i}]"))
        return out
    out[prefix] = str(schema)
    return out


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


async def register_payload_snapshot(
    db: AsyncSession,
    *,
    service_name: str,
    http_method: str,
    route_path: str,
    fingerprint: str,
    normalized_schema: Any,
) -> tuple[str, bool]:
    lock_id = route_lock_id(route_path)
    async with db.begin():
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )
        endpoint_id = await ensure_endpoint(
            db,
            service_name=service_name,
            http_method=http_method,
            route_path=route_path,
        )
        inserted = await register_snapshot(
            db,
            endpoint_id=endpoint_id,
            fingerprint=fingerprint,
            normalized_schema=normalized_schema,
        )
    return endpoint_id, inserted


async def get_active_baseline(db: AsyncSession, endpoint_id: str) -> dict[str, Any] | None:
    row = await db.execute(
        text(
            """
            SELECT normalized_schema
            FROM schema_snapshots
            WHERE endpoint_id = :endpoint_id::uuid
              AND is_active_baseline = TRUE
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"endpoint_id": endpoint_id},
    )
    return row.scalar_one_or_none()


def structural_diff(
    baseline_schema: dict[str, Any],
    incoming_schema: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline_flat = _flatten_schema(baseline_schema)
    incoming_flat = _flatten_schema(incoming_schema)

    diffs: list[dict[str, Any]] = []
    for path in sorted(baseline_flat.keys() | incoming_flat.keys()):
        old = baseline_flat.get(path)
        new = incoming_flat.get(path)
        if old == new:
            continue
        diffs.append({"path": path, "old": old, "new": new, "severity": None})
    return diffs


def classify_safe_changes(diffs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in diffs:
        if item["old"] is None and item["new"] is not None:
            item["severity"] = "SAFE"
    return diffs


def classify_risky_mutations(diffs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    primitive_types = {"int", "float", "string", "bool"}
    for item in diffs:
        if item["severity"] is not None:
            continue
        if item["old"] in primitive_types and item["new"] in primitive_types and item["old"] != item["new"]:
            item["severity"] = "RISKY"
    return diffs


async def log_drift_violations(
    db: AsyncSession,
    *,
    endpoint_id: str,
    fingerprint: str,
    diffs: list[dict[str, Any]],
) -> None:
    for item in diffs:
        if item["severity"] is None:
            continue
        await db.execute(
            text(
                """
                INSERT INTO contract_drift_violations(endpoint_id, observed_fingerprint, severity, diff_payload)
                VALUES (:endpoint_id::uuid, :fingerprint, CAST(:severity AS change_severity), CAST(:diff_payload AS jsonb))
                """
            ),
            {
                "endpoint_id": endpoint_id,
                "fingerprint": fingerprint,
                "severity": item["severity"],
                "diff_payload": json.dumps({"path": item["path"], "old": item["old"], "new": item["new"]}),
            },
        )
