from __future__ import annotations

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
from app.runtime.events import EventPublisher

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://schemapilot:dev@localhost:55433/schemapilot_runtime")
DATABASE_URL_SYNC = os.getenv("DATABASE_URL_SYNC", "postgresql://schemapilot:dev@localhost:55433/schemapilot_runtime")


class _CapturePublisher(EventPublisher):
    def __init__(self) -> None:
        self.events = []

    async def publish_drift_detected(self, event):
        self.events.append(event)


@pytest.fixture(scope="session", autouse=True)
def _runtime_migrations() -> None:
    env = os.environ.copy()
    env.setdefault("DATABASE_URL_SYNC", DATABASE_URL_SYNC)
    subprocess.run(["python", "scripts/apply_runtime_migrations.py"], check=True, env=env)


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    e = create_async_engine(DATABASE_URL, future=True)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        for tbl in [
            "webhook_delivery_dlq",
            "webhook_delivery_attempts",
            "consumer_subscriptions",
            "contract_schema_versions",
            "contract_registry_endpoints",
        ]:
            await session.execute(text(f"DELETE FROM {tbl}"))
        await session.commit()
    return maker


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


@pytest.mark.asyncio
async def test_same_fingerprint_allowed_different_endpoints(client: httpx.AsyncClient):
    p = {"id": 1}
    a = await client.post("/track", json={"namespace": "n", "service_name": "a", "http_method": "POST", "route_path": "/x", "payload": p})
    b = await client.post("/track", json={"namespace": "n", "service_name": "a", "http_method": "POST", "route_path": "/y", "payload": p})
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["endpoint_id"] != b.json()["endpoint_id"]


@pytest.mark.asyncio
async def test_version_increment_behavior(client: httpx.AsyncClient):
    r1 = await client.post("/track", json={"namespace": "n", "service_name": "svc", "http_method": "POST", "route_path": "/orders", "payload": {"score": 1}})
    r2 = await client.post("/track", json={"namespace": "n", "service_name": "svc", "http_method": "POST", "route_path": "/orders", "payload": {"score": 1.5}})
    assert r1.json()["schema_version"] == 1
    assert r2.json()["schema_version"] == 2


@pytest.mark.asyncio
async def test_baseline_promotion_is_current_single(session_maker: async_sessionmaker[AsyncSession], client: httpx.AsyncClient):
    await client.post("/track", json={"namespace": "n", "service_name": "svc", "http_method": "POST", "route_path": "/orders", "payload": {"score": 1}})
    await client.post("/track", json={"namespace": "n", "service_name": "svc", "http_method": "POST", "route_path": "/orders", "payload": {"score": 2}})
    async with session_maker() as session:
        row = await session.execute(text("SELECT COUNT(*) FROM contract_schema_versions WHERE is_current = TRUE"))
        assert row.scalar_one() == 1


@pytest.mark.asyncio
async def test_subscription_threshold_and_inactive_filtering(client: httpx.AsyncClient):
    r = await client.post("/track", json={"namespace": "n", "service_name": "svc", "http_method": "POST", "route_path": "/o", "payload": {"score": 1}})
    endpoint_id = r.json()["endpoint_id"]

    active = await client.post("/api/v1/subscriptions", json={
        "consumer_id": "c1", "endpoint_id": endpoint_id, "target_url": "http://test/webhook", "severity_threshold": "RISKY", "active": True
    })
    inactive = await client.post("/api/v1/subscriptions", json={
        "consumer_id": "c2", "endpoint_id": endpoint_id, "target_url": "http://test/webhook", "severity_threshold": "SAFE", "active": False
    })
    assert active.status_code == 200 and inactive.status_code == 200

    r2 = await client.post("/track", json={"namespace": "n", "service_name": "svc", "http_method": "POST", "route_path": "/o", "payload": {"score": 1.5}})
    body = r2.json()
    assert body["compatibility_classification"] == "RISKY"
    assert body["affected_consumer_count"] == 1


@pytest.mark.asyncio
async def test_metrics_endpoint_exposed(client: httpx.AsyncClient):
    res = await client.get("/metrics")
    assert res.status_code == 200
    assert b"drift_detection_latency_seconds" in res.content


@pytest.mark.asyncio
async def test_webhook_dlq_persisted_on_failure(session_maker: async_sessionmaker[AsyncSession], client: httpx.AsyncClient):
    r = await client.post("/track", json={"namespace": "n", "service_name": "svc", "http_method": "POST", "route_path": "/w", "payload": {"score": 1}})
    endpoint_id = r.json()["endpoint_id"]
    await client.post("/api/v1/subscriptions", json={
        "consumer_id": "c1", "endpoint_id": endpoint_id, "target_url": "http://127.0.0.1:9/fail", "severity_threshold": "SAFE", "active": True
    })
    await client.post("/track", json={"namespace": "n", "service_name": "svc", "http_method": "POST", "route_path": "/w", "payload": {"score": 2.5}})

    async with session_maker() as session:
        q = await session.execute(text("SELECT COUNT(*) FROM webhook_delivery_dlq"))
        assert q.scalar_one() >= 1
