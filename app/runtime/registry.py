from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.runtime.models import SchemaVersionRecord
from app.runtime.metrics import ADVISORY_LOCK_WAIT_SECONDS


def _lock_id(namespace: str, service_name: str, method: str, route: str) -> int:
    key = f"{namespace}:{service_name}:{method}:{route}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return int(digest, 16) % 2147483647


async def ensure_endpoint(
    db: AsyncSession,
    *,
    namespace: str,
    service_name: str,
    http_method: str,
    route_path: str,
) -> tuple[str, str]:
    endpoint_name = f"{service_name} {http_method} {route_path}"
    created = await db.execute(
        text(
            """
            INSERT INTO contract_registry_endpoints(namespace, service_name, http_method, route_path, endpoint_name)
            VALUES (:namespace, :service_name, :http_method, :route_path, :endpoint_name)
            ON CONFLICT (namespace, service_name, http_method, route_path)
            DO NOTHING
            RETURNING id::text, endpoint_name
            """
        ),
        {
            "namespace": namespace,
            "service_name": service_name,
            "http_method": http_method,
            "route_path": route_path,
            "endpoint_name": endpoint_name,
        },
    )
    row = created.first()
    if row is None:
        existing = await db.execute(
            text(
                """
                SELECT id::text, endpoint_name
                FROM contract_registry_endpoints
                WHERE namespace = :namespace
                  AND service_name = :service_name
                  AND http_method = :http_method
                  AND route_path = :route_path
                """
            ),
            {
                "namespace": namespace,
                "service_name": service_name,
                "http_method": http_method,
                "route_path": route_path,
            },
        )
        row = existing.one()
    endpoint_id, name = row
    return endpoint_id, name


async def get_current_schema(db: AsyncSession, endpoint_id: str) -> SchemaVersionRecord | None:
    row = await db.execute(
        text(
            """
            SELECT id::text, endpoint_id::text, version, fingerprint, canonical_schema,
                   compatibility_classification, previous_version_id::text, is_current
            FROM contract_schema_versions
            WHERE endpoint_id = CAST(:endpoint_id AS uuid)
              AND is_current = TRUE
            ORDER BY version DESC
            LIMIT 1
            """
        ),
        {"endpoint_id": endpoint_id},
    )
    item = row.first()
    if item is None:
        return None
    return SchemaVersionRecord(
        id=item[0],
        endpoint_id=item[1],
        version=item[2],
        fingerprint=item[3],
        canonical_schema=item[4],
        compatibility_classification=item[5],
        previous_version_id=item[6],
        is_current=item[7],
    )


async def upsert_schema_version(
    db: AsyncSession,
    *,
    namespace: str,
    service_name: str,
    http_method: str,
    route_path: str,
    fingerprint: str,
    canonical_schema: dict[str, Any],
    classification: str,
) -> tuple[str, str, SchemaVersionRecord, bool]:
    endpoint_id, endpoint_name = await ensure_endpoint(
        db,
        namespace=namespace,
        service_name=service_name,
        http_method=http_method,
        route_path=route_path,
    )

    existing_fast = await db.execute(
        text(
            """
            SELECT id::text, endpoint_id::text, version, fingerprint, canonical_schema,
                   compatibility_classification, previous_version_id::text, is_current
            FROM contract_schema_versions
            WHERE endpoint_id = CAST(:endpoint_id AS uuid)
              AND fingerprint = :fingerprint
            LIMIT 1
            """
        ),
        {"endpoint_id": endpoint_id, "fingerprint": fingerprint},
    )
    fast_row = existing_fast.first()
    if fast_row is not None:
        return endpoint_id, endpoint_name, SchemaVersionRecord(
            id=fast_row[0], endpoint_id=fast_row[1], version=fast_row[2], fingerprint=fast_row[3],
            canonical_schema=fast_row[4], compatibility_classification=fast_row[5],
            previous_version_id=fast_row[6], is_current=fast_row[7]
        ), False

    lock = _lock_id(namespace, service_name, http_method, route_path)
    lock_start = time.perf_counter()
    await db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": lock})
    ADVISORY_LOCK_WAIT_SECONDS.observe(time.perf_counter() - lock_start)

    current = await get_current_schema(db, endpoint_id)

    existing = await db.execute(
        text(
            """
            SELECT id::text, endpoint_id::text, version, fingerprint, canonical_schema,
                   compatibility_classification, previous_version_id::text, is_current
            FROM contract_schema_versions
            WHERE endpoint_id = CAST(:endpoint_id AS uuid)
              AND fingerprint = :fingerprint
            LIMIT 1
            """
        ),
        {"endpoint_id": endpoint_id, "fingerprint": fingerprint},
    )
    found = existing.first()
    if found is not None:
        return endpoint_id, endpoint_name, SchemaVersionRecord(
            id=found[0], endpoint_id=found[1], version=found[2], fingerprint=found[3],
            canonical_schema=found[4], compatibility_classification=found[5],
            previous_version_id=found[6], is_current=found[7]
        ), False

    next_version = 1 if current is None else current.version + 1
    previous_id = None if current is None else current.id

    if current is not None:
        await db.execute(
            text(
                "UPDATE contract_schema_versions SET is_current = FALSE WHERE id = CAST(:id AS uuid)"
            ),
            {"id": current.id},
        )

    inserted = await db.execute(
        text(
            """
            INSERT INTO contract_schema_versions(
              endpoint_id, version, fingerprint, canonical_schema,
              compatibility_classification, previous_version_id, is_current
            )
            VALUES (
              CAST(:endpoint_id AS uuid), :version, :fingerprint, CAST(:canonical_schema AS jsonb),
              :classification, CAST(:previous_version_id AS uuid), TRUE
            )
            RETURNING id::text
            """
        ),
        {
            "endpoint_id": endpoint_id,
            "version": next_version,
            "fingerprint": fingerprint,
            "canonical_schema": json.dumps(canonical_schema),
            "classification": classification,
            "previous_version_id": previous_id,
        },
    )
    version_id = inserted.scalar_one()

    return endpoint_id, endpoint_name, SchemaVersionRecord(
        id=version_id,
        endpoint_id=endpoint_id,
        version=next_version,
        fingerprint=fingerprint,
        canonical_schema=canonical_schema,
        compatibility_classification=classification,
        previous_version_id=previous_id,
        is_current=True,
    ), True
