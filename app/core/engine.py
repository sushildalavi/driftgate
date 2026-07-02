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
        text(
            """
            SELECT 1
            FROM schema_snapshots
            WHERE endpoint_id = CAST(:endpoint_id AS uuid)
              AND fingerprint = :fingerprint
            """
        ),
        {"endpoint_id": endpoint_id, "fingerprint": fingerprint},
    )
    if existing.scalar_one_or_none():
        return False

    await db.execute(
        text(
            """
            INSERT INTO schema_snapshots(fingerprint, endpoint_id, normalized_schema)
            VALUES (:fingerprint, CAST(:endpoint_id AS uuid), CAST(:normalized_schema AS jsonb))
            """
        ),
        {
            "fingerprint": fingerprint,
            "endpoint_id": endpoint_id,
            "normalized_schema": json.dumps(normalized_schema),
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
            WHERE endpoint_id = CAST(:endpoint_id AS uuid)
              AND is_active_baseline = TRUE
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"endpoint_id": endpoint_id},
    )
    return row.scalar_one_or_none()


async def get_active_baseline_snapshot(db: AsyncSession, endpoint_id: str) -> dict[str, Any] | None:
    row = await db.execute(
        text(
            """
            SELECT fingerprint, normalized_schema
            FROM schema_snapshots
            WHERE endpoint_id = CAST(:endpoint_id AS uuid)
              AND is_active_baseline = TRUE
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"endpoint_id": endpoint_id},
    )
    baseline_row = row.first()
    if baseline_row is None:
        return None
    return {"fingerprint": baseline_row[0], "normalized_schema": baseline_row[1]}


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
        old = item["old"]
        new = item["new"]
        if old in primitive_types and new in primitive_types and old != new:
            if old == "int" and new == "float":
                item["severity"] = "RISKY"
            elif old == "float" and new == "int":
                item["severity"] = "BREAKING"
            else:
                item["severity"] = "BREAKING"
    return diffs


def classify_breaking_changes(diffs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in diffs:
        if item["severity"] is not None:
            continue
        if item["old"] is not None and item["new"] is None:
            item["severity"] = "BREAKING"
            continue
        if isinstance(item["old"], str) and item["old"].startswith("nullable_"):
            required_old = item["old"].replace("nullable_", "", 1)
            if item["new"] == required_old:
                item["severity"] = "BREAKING"
    return diffs


def classify_contract_drift(diffs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    classify_safe_changes(diffs)
    classify_risky_mutations(diffs)
    classify_breaking_changes(diffs)
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
                VALUES (CAST(:endpoint_id AS uuid), :fingerprint, CAST(:severity AS change_severity), CAST(:diff_payload AS jsonb))
                """
            ),
            {
                "endpoint_id": endpoint_id,
                "fingerprint": fingerprint,
                "severity": item["severity"],
                "diff_payload": json.dumps({"path": item["path"], "old": item["old"], "new": item["new"]}),
            },
        )


async def get_runtime_metrics(db: AsyncSession) -> dict:
    ep_res = await db.execute(text("SELECT COUNT(*) FROM api_endpoints;"))
    ep_count = ep_res.scalar_one()

    ss_res = await db.execute(text("SELECT COUNT(*) FROM schema_snapshots;"))
    ss_count = ss_res.scalar_one()

    viol_res = await db.execute(
        text(
            """
            SELECT severity, COUNT(*)
            FROM contract_drift_violations
            GROUP BY severity;
            """
        )
    )
    severity_counts = {row[0]: row[1] for row in viol_res.fetchall()}
    drift_dlq_res = await db.execute(text("SELECT COUNT(*) FROM drift_event_dlq;"))
    webhook_dlq_res = await db.execute(text("SELECT COUNT(*) FROM webhook_delivery_dlq;"))
    outbox_pending_res = await db.execute(
        text("SELECT COUNT(*) FROM webhook_outbox WHERE status = 'PENDING';")
    )

    return {
        "endpoint_count": ep_count,
        "snapshot_count": ss_count,
        "severity_counts": severity_counts,
        "webhook_delivery_dlq_count": webhook_dlq_res.scalar_one(),
        "webhook_outbox_pending_count": outbox_pending_res.scalar_one(),
        "drift_event_dlq_count": drift_dlq_res.scalar_one(),
    }
