from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import psycopg2

TRACK_URL = os.getenv("TRACK_URL", "http://localhost:8302/track")
REQUESTS = int(os.getenv("SIM_REQUESTS", "5000"))
CONCURRENCY = int(os.getenv("SIM_CONCURRENCY", "200"))
OUTPUT_PATH = Path(
    os.getenv(
        "SIM_OUTPUT_PATH",
        "docs/benchmarks/schema_pilot_simulation_5000.json",
    )
)


@dataclass
class SimulationResult:
    total: int
    success: int
    failure: int


def payload_variant(i: int) -> dict[str, Any]:
    base: dict[str, Any] = {
        "user_id": i,
        "meta": {"tags": ["admin", "staff"], "active": True},
        "score": 42,
        "price": 42.5,
    }
    phase = i % 5
    if phase == 1:
        base["optional"] = None
    elif phase == 2:
        base["score"] = 42.5
    elif phase == 3:
        base["price"] = 42
    elif phase == 4:
        base.pop("meta")
    return base


async def _submit(client: httpx.AsyncClient, i: int) -> bool:
    body = {
        "service_name": "chaos-client",
        "http_method": "POST",
        "route_path": "/mocked/contracts",
        "payload": payload_variant(i),
    }
    try:
        r = await client.post(TRACK_URL, json=body)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


async def run_simulation() -> SimulationResult:
    sem = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient(timeout=15) as client:
        async def bounded(i: int) -> bool:
            async with sem:
                await asyncio.sleep(random.random() * 0.01)
                return await _submit(client, i)

        results = await asyncio.gather(*(bounded(i) for i in range(REQUESTS)))

    success = sum(1 for ok in results if ok)
    return SimulationResult(total=REQUESTS, success=success, failure=REQUESTS - success)


async def main() -> None:
    start = time.perf_counter()
    dsn = os.getenv("DATABASE_URL_SYNC", "postgresql://schemapilot:dev@localhost:55433/schemapilot_runtime")
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM contract_drift_violations")
            cur.execute("DELETE FROM schema_snapshots")
            cur.execute("DELETE FROM api_endpoints")
            conn.commit()

    result = await run_simulation()
    print(f"total={result.total} success={result.success} failure={result.failure}")
    assert result.failure == 0, "simulation encountered failed submissions"

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM api_endpoints WHERE route_path = %s", ("/mocked/contracts",))
            endpoint_count = cur.fetchone()[0]
            cur.execute(
                """
                SELECT COUNT(*)
                FROM schema_snapshots
                WHERE endpoint_id IN (
                    SELECT id FROM api_endpoints WHERE route_path = %s
                )
                """,
                ("/mocked/contracts",),
            )
            snapshot_count = cur.fetchone()[0]
            cur.execute(
                """
                SELECT severity, COUNT(*)
                FROM contract_drift_violations
                GROUP BY severity
                ORDER BY severity
                """
            )
            severity_rows = cur.fetchall()
            cur.execute(
                """
                SELECT COALESCE(SUM(active_count - 1), 0)
                FROM (
                    SELECT endpoint_id, COUNT(*) AS active_count
                    FROM schema_snapshots
                    WHERE is_active_baseline = TRUE
                    GROUP BY endpoint_id
                    HAVING COUNT(*) > 1
                ) dup
                """
            )
            duplicate_baselines = cur.fetchone()[0]

    assert endpoint_count == 1, f"expected exactly one endpoint row, got {endpoint_count}"
    assert snapshot_count >= 1, "expected at least one schema snapshot"
    severity_counts = {sev: count for sev, count in severity_rows}

    async with httpx.AsyncClient(timeout=15) as client:
        metrics_url = TRACK_URL.rsplit("/track", 1)[0] + "/api/v1/metrics"
        metrics_res = await client.get(metrics_url)
        assert metrics_res.status_code == 200, f"metrics endpoint failed: {metrics_res.status_code}"
        metrics_json = metrics_res.json()

    print(
        "metrics:",
        {
            "endpoint_count": endpoint_count,
            "snapshot_count": snapshot_count,
            "severity_counts": severity_counts,
            "metrics_endpoint": metrics_json,
        },
    )
    assert severity_counts.get("SAFE", 0) > 0, "expected SAFE drift logs"
    assert severity_counts.get("RISKY", 0) > 0, "expected RISKY drift logs"
    assert severity_counts.get("BREAKING", 0) > 0, "expected BREAKING drift logs"
    duration = time.perf_counter() - start

    artifact = {
        "events_total": result.total,
        "concurrency": CONCURRENCY,
        "success_count": result.success,
        "failure_count": result.failure,
        "safe_count": severity_counts.get("SAFE", 0),
        "risky_count": severity_counts.get("RISKY", 0),
        "breaking_count": severity_counts.get("BREAKING", 0),
        "duplicate_baselines": int(duplicate_baselines),
        "duration_seconds": round(duration, 4),
        "command_used": " ".join(sys.argv),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2))
    print(f"wrote artifact: {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
