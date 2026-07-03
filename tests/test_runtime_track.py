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
from app.runtime.contract_review import (
    ContractReviewOutcome,
    ContractReviewService,
    FakeReviewProvider,
    ReviewDecision,
    ReviewSeverity,
)
from app.runtime.document_store import InMemoryDocumentStore
from app.runtime import webhook as webhook_runtime

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://driftgate:dev@localhost:55433/driftgate_runtime",
)
DATABASE_URL_SYNC = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://driftgate:dev@localhost:55433/driftgate_runtime",
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
                  drift_event_dlq,
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
    app.state.document_store = InMemoryDocumentStore()
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


@pytest.mark.asyncio
async def test_track_persists_document_store_artifacts(client: httpx.AsyncClient) -> None:
    base = {
        "service_name": "svc-a",
        "http_method": "POST",
        "route_path": "/v1/orders",
        "payload": _payload(include_meta=True),
    }
    await client.post("/track", json=base)
    await client.post(
        "/track",
        json={
            **base,
            "payload": _payload(score=42.5, include_meta=False),
        },
    )

    store = app.state.document_store
    payload_snapshots = await store.list_payload_snapshots()
    schema_diffs = await store.list_schema_diffs()

    assert len(payload_snapshots) == 2
    assert payload_snapshots[0]["kind"] == "payload_snapshot"
    assert len(schema_diffs) == 1
    assert schema_diffs[0]["kind"] == "schema_diff"
    assert schema_diffs[0]["classification"] == "BREAKING"


@pytest.mark.asyncio
async def test_validation_errors_are_captured_in_document_store(client: httpx.AsyncClient) -> None:
    res = await client.post(
        "/track",
        json={
            "service_name": "svc-a",
            "http_method": "POST",
            "route_path": "/v1/orders",
        },
    )
    assert res.status_code == 422

    store = app.state.document_store
    validation_errors = await store.list_validation_errors()
    assert len(validation_errors) == 1
    assert validation_errors[0]["kind"] == "validation_error"
    assert validation_errors[0]["path"] == "/track"


@pytest.mark.asyncio
async def test_dlq_list_and_replay_endpoints(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    r = await client.post(
        "/track",
        json={
            "service_name": "svc-a",
            "http_method": "POST",
            "route_path": "/v1/orders",
            "payload": _payload(include_meta=True),
        },
    )
    endpoint_id = r.json()["endpoint_id"]
    sub = await client.post(
        "/api/v1/subscriptions",
        json={
            "consumer_id": "c1",
            "endpoint_id": endpoint_id,
            "target_url": "http://127.0.0.1:9/fail",
            "severity_threshold": "SAFE",
            "active": True,
        },
    )
    assert sub.status_code == 200

    await client.post(
        "/track",
        json={
            "service_name": "svc-a",
            "http_method": "POST",
            "route_path": "/v1/orders",
            "payload": _payload(score=42.5, include_meta=False),
        },
    )

    dlq_response = await client.get("/api/v1/webhook-dlq")
    assert dlq_response.status_code == 200
    dlq_entries = dlq_response.json()
    assert len(dlq_entries) >= 1
    dlq_id = dlq_entries[0]["id"]

    async def fake_replay(*_args, **_kwargs) -> bool:
        return True

    monkeypatch.setattr(webhook_runtime, "deliver_with_retry", fake_replay)

    replay_response = await client.post(f"/api/v1/webhook-dlq/{dlq_id}/replay")
    assert replay_response.status_code == 200
    assert replay_response.json()["replayed"] is True

    store = app.state.document_store
    artifacts = await store.list_replay_artifacts()
    assert len(artifacts) == 1
    assert artifacts[0]["payload"]["dlq_id"] == dlq_id


@pytest.mark.asyncio
async def test_document_store_browse_endpoints(client: httpx.AsyncClient) -> None:
    await client.post(
        "/track",
        json={
            "service_name": "svc-a",
            "http_method": "POST",
            "route_path": "/v1/orders",
            "payload": _payload(include_meta=True),
        },
    )
    await client.post(
        "/track",
        json={
            "service_name": "svc-a",
            "http_method": "POST",
            "route_path": "/v1/orders",
            "payload": _payload(score=42.5, include_meta=False),
        },
    )

    payloads = await client.get("/api/v1/documents/payload-snapshots")
    diffs = await client.get("/api/v1/documents/schema-diffs")
    validations = await client.get("/api/v1/documents/validation-errors")

    assert payloads.status_code == 200
    assert diffs.status_code == 200
    assert validations.status_code == 200
    assert len(payloads.json()) == 2
    assert len(diffs.json()) == 1


@pytest.mark.asyncio
async def test_contract_review_api_and_history(client: httpx.AsyncClient) -> None:
    review = ContractReviewOutcome(
        decision=ReviewDecision.NEEDS_CHANGES,
        severity=ReviewSeverity.RISKY,
        summary="Schema change is risky",
        consumer_impact="1 active consumer",
        evidence=["[snapshot:1] safe baseline", "[schema-diff:1] nullable change"],
        recommended_fixes=["Keep the field optional until consumers are updated."],
        migration_note="Roll out a compatibility layer first.",
        review_comment="### Review\nRisky change with grounded evidence.",
        confidence=0.91,
        insufficient_evidence=False,
    )
    app.state.contract_review_service = ContractReviewService(provider=FakeReviewProvider(outcome=review))

    base = {
        "service_name": "svc-a",
        "http_method": "POST",
        "route_path": "/v1/orders",
        "payload": _payload(include_meta=True),
    }
    created = await client.post("/track", json=base)
    endpoint_id = created.json()["endpoint_id"]
    await client.post(
        "/track",
        json={
            **base,
            "payload": _payload(score=42.5, include_meta=False),
        },
    )

    response = await client.post("/api/v1/ai/contract-review", json={"endpoint_id": endpoint_id})
    assert response.status_code == 200
    body = response.json()
    assert body["review"]["decision"] == "needs_changes"
    assert body["review"]["severity"] == "risky"
    assert body["review"]["confidence"] == pytest.approx(0.91)

    history = await client.get("/api/v1/ai/contract-reviews", params={"endpoint_id": endpoint_id})
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["review"]["decision"] == "needs_changes"
