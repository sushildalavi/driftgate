from __future__ import annotations

import copy

import pytest

from app.runtime.document_store import (
    InMemoryDocumentStore,
    MongoDocumentStore,
    build_document_store,
)


@pytest.mark.asyncio
async def test_in_memory_document_store_round_trips_documents() -> None:
    store = InMemoryDocumentStore()

    snapshot = await store.store_payload_snapshot(
        namespace="gateway",
        service_name="shop",
        http_method="POST",
        route_path="/webhooks/shop",
        payload={"order_id": 1},
        fingerprint="abc123",
        classification="SAFE",
        source="runtime-track",
    )
    diff = await store.store_schema_diff(
        endpoint_id="endpoint-1",
        endpoint_name="shop POST /webhooks/shop",
        namespace="gateway",
        service_name="shop",
        http_method="POST",
        route_path="/webhooks/shop",
        old_fingerprint="old",
        new_fingerprint="new",
        old_version=1,
        new_version=2,
        classification="BREAKING",
        diffs=[{"path": "items[*].price", "change_type": "removed_required"}],
        source="runtime-track",
    )
    validation_error = await store.store_validation_error(
        source="gateway",
        path="/webhooks/shop",
        errors=[{"loc": ["body"], "msg": "invalid"}],
        raw_body="{",
    )
    replay = await store.store_replay_artifact(
        source="runtime",
        artifact_type="revalidation",
        payload={"run_id": "r1"},
    )
    review = await store.store_contract_review(
        endpoint_id="endpoint-1",
        endpoint_name="shop POST /webhooks/shop",
        provider="fake",
        model_name="fake",
        evidence_summary="safe baseline",
        consumer_impact="No active consumers",
        review={"decision": "approve", "severity": "compatible"},
        context={"endpoint_id": "endpoint-1"},
        source="runtime-contract-review",
    )

    assert snapshot["kind"] == "payload_snapshot"
    assert diff["classification"] == "BREAKING"
    assert validation_error["kind"] == "validation_error"
    assert replay["kind"] == "replay_artifact"
    assert review["kind"] == "contract_review"

    fetched = await store.get_payload_snapshot(snapshot["document_id"])
    assert fetched is not None
    assert fetched["payload"] == {"order_id": 1}

    documents = await store.list_payload_snapshots()
    assert [doc["document_id"] for doc in documents] == [snapshot["document_id"]]
    reviews = await store.list_contract_reviews()
    assert len(reviews) == 1
    assert reviews[0]["kind"] == "contract_review"


@pytest.mark.asyncio
async def test_mongo_document_store_uses_injected_client() -> None:
    class FakeInsertResult:
        def __init__(self, inserted_id: str) -> None:
            self.inserted_id = inserted_id

    class FakeCursor:
        def __init__(self, documents: list[dict[str, object]]) -> None:
            self._documents = documents

        def sort(self, *_args, **_kwargs) -> "FakeCursor":
            return self

        def limit(self, *_args, **_kwargs) -> "FakeCursor":
            return self

        async def to_list(self, length: int | None = None) -> list[dict[str, object]]:
            documents = self._documents if length is None else self._documents[:length]
            return [copy.deepcopy(document) for document in documents]

    class FakeCollection:
        def __init__(self) -> None:
            self.documents: dict[str, dict[str, object]] = {}

        async def insert_one(self, document: dict[str, object]) -> FakeInsertResult:
            self.documents[str(document["_id"])] = copy.deepcopy(document)
            return FakeInsertResult(str(document["_id"]))

        async def find_one(self, filter: dict[str, object]) -> dict[str, object] | None:
            document_id = str(filter["_id"])
            document = self.documents.get(document_id)
            return copy.deepcopy(document) if document is not None else None

        def find(self, *_args, **_kwargs) -> FakeCursor:
            return FakeCursor(list(self.documents.values()))

    class FakeDatabase:
        def __init__(self) -> None:
            self.collections: dict[str, FakeCollection] = {}

        def __getitem__(self, collection: str) -> FakeCollection:
            self.collections.setdefault(collection, FakeCollection())
            return self.collections[collection]

    class FakeClient:
        def __init__(self) -> None:
            self.database = FakeDatabase()
            self.closed = False

        def __getitem__(self, _name: str) -> FakeDatabase:
            return self.database

        def close(self) -> None:
            self.closed = True

    client = FakeClient()
    store = MongoDocumentStore("mongodb://unused", client=client)

    snapshot = await store.store_payload_snapshot(
        namespace="gateway",
        service_name="shop",
        http_method="POST",
        route_path="/webhooks/shop",
        payload={"order_id": 2},
        fingerprint="abc123",
        classification="SAFE",
        source="runtime-track",
    )

    fetched = await store.get_payload_snapshot(snapshot["document_id"])
    assert fetched is not None
    assert fetched["payload"] == {"order_id": 2}

    listed = await store.list_payload_snapshots()
    assert listed[0]["document_id"] == snapshot["document_id"]

    await store.aclose()
    assert client.closed is True


def test_build_document_store_defaults_to_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCUMENT_STORE_BACKEND", raising=False)
    monkeypatch.delenv("DOCUMENT_STORE_URI", raising=False)
    store = build_document_store()
    assert isinstance(store, InMemoryDocumentStore)


def test_build_document_store_requires_uri_for_mongo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCUMENT_STORE_BACKEND", "mongo")
    monkeypatch.delenv("DOCUMENT_STORE_URI", raising=False)

    with pytest.raises(RuntimeError, match="DOCUMENT_STORE_URI"):
        build_document_store()
