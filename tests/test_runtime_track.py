from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db import get_db
from app.main import app

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://schemapilot:dev@localhost:55433/schemapilot_runtime",
)
DATABASE_URL_SYNC = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://schemapilot:dev@localhost:55433/schemapilot_runtime",
)


@pytest.fixture(scope="session", autouse=True)
def _runtime_migrations() -> None:
    env = os.environ.copy()
    env.setdefault("DATABASE_URL_SYNC", DATABASE_URL_SYNC)
    subprocess.run(
        ["python", "scripts/apply_runtime_migrations.py"],
        check=True,
        env=env,
    )


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    e = create_async_engine(DATABASE_URL, future=True)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        await session.execute(
            text(
                """
                TRUNCATE TABLE
                  webhook_delivery_dlq,
                  webhook_delivery_attempts,
                  consumer_subscriptions,
                  contract_schema_versions,
                  contract_registry_endpoints,
                  contract_drift_violations,
                  schema_snapshots,
                  api_endpoints
                RESTART IDENTITY CASCADE
                """
            )
        )
        await session.commit()
    return maker


@pytest_asyncio.fixture
async def db_session(session_maker: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncSession, None]:
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(session_maker: async_sessionmaker[AsyncSession]) -> AsyncGenerator[httpx.AsyncClient, None]:
    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _payload(score: float | int = 42, include_meta: bool = True) -> dict:
    p = {"user_id": 1, "score": score, "price": 42.5}
    if include_meta:
        p["meta"] = {"active": True}
    return p


@pytest.mark.asyncio
async def test_track_creates_baseline_safe(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    res = await client.post(
        "/track",
        json={
            "service_name": "svc-a",
            "http_method": "POST",
            "route_path": "/v1/orders",
            "payload": _payload(),
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["inserted"] is True
    assert body["diff_count"] == 0

    count = await db_session.execute(text("SELECT COUNT(*) FROM schema_snapshots"))
    assert count.scalar_one() == 1


@pytest.mark.asyncio
async def test_track_classifies_risky(client: httpx.AsyncClient) -> None:
    base = {
        "service_name": "svc-a",
        "http_method": "POST",
        "route_path": "/v1/orders",
        "payload": _payload(score=42),
    }
    await client.post("/track", json=base)
    risky = {
        **base,
        "payload": _payload(score=42.5),
    }
    res = await client.post("/track", json=risky)
    assert res.status_code == 200
    assert res.json()["severities"]["RISKY"] > 0


@pytest.mark.asyncio
async def test_track_classifies_breaking(client: httpx.AsyncClient) -> None:
    base = {
        "service_name": "svc-a",
        "http_method": "POST",
        "route_path": "/v1/orders",
        "payload": _payload(include_meta=True),
    }
    await client.post("/track", json=base)
    breaking = {
        **base,
        "payload": _payload(include_meta=False),
    }
    res = await client.post("/track", json=breaking)
    assert res.status_code == 200
    assert res.json()["severities"]["BREAKING"] > 0


@pytest.mark.asyncio
async def test_endpoint_scoped_fingerprint_uniqueness(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    req1 = {
        "service_name": "svc-a",
        "http_method": "POST",
        "route_path": "/v1/orders",
        "payload": _payload(),
    }
    req2 = {
        "service_name": "svc-b",
        "http_method": "POST",
        "route_path": "/v1/payments",
        "payload": _payload(),
    }
    r1 = await client.post("/track", json=req1)
    r2 = await client.post("/track", json=req2)
    assert r1.status_code == 200 and r2.status_code == 200

    rows = await db_session.execute(text("SELECT COUNT(*) FROM schema_snapshots"))
    assert rows.scalar_one() == 2


@pytest.mark.asyncio
async def test_concurrent_submissions_keep_single_baseline(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    async def submit() -> int:
        res = await client.post(
            "/track",
            json={
                "service_name": "svc-a",
                "http_method": "POST",
                "route_path": "/v1/orders",
                "payload": _payload(),
            },
        )
        return res.status_code

    statuses = await asyncio.gather(*[submit() for _ in range(50)])
    assert all(s == 200 for s in statuses)

    ep_count = await db_session.execute(text("SELECT COUNT(*) FROM api_endpoints"))
    assert ep_count.scalar_one() == 1
    baseline_count = await db_session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM schema_snapshots
            WHERE is_active_baseline = TRUE
            """
        )
    )
    assert baseline_count.scalar_one() == 1


@pytest.mark.asyncio
async def test_metrics_consistency(client: httpx.AsyncClient) -> None:
    await client.post(
        "/track",
        json={
            "service_name": "svc-a",
            "http_method": "POST",
            "route_path": "/v1/orders",
            "payload": _payload(),
        },
    )
    await client.post(
        "/track",
        json={
            "service_name": "svc-a",
            "http_method": "POST",
            "route_path": "/v1/orders",
            "payload": _payload(score=42.5),
        },
    )
    metrics = await client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    m = metrics.json()
    assert m["endpoint_count"] == 1
    assert m["snapshot_count"] >= 1
    assert m["severity_counts"].get("RISKY", 0) > 0
