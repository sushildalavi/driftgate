from __future__ import annotations

import copy
import inspect
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from pymongo import AsyncMongoClient

DEFAULT_DATABASE_NAME = "driftgate_documents"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _document(kind: str, **fields: Any) -> dict[str, Any]:
    document_id = uuid.uuid4().hex
    document = {
        "_id": document_id,
        "document_id": document_id,
        "kind": kind,
        "created_at": _now(),
    }
    document.update(copy.deepcopy(fields))
    return document


@runtime_checkable
class DocumentStore(Protocol):
    async def store_payload_snapshot(
        self,
        *,
        endpoint_id: str | None = None,
        namespace: str,
        service_name: str,
        http_method: str,
        route_path: str,
        payload: dict[str, Any],
        fingerprint: str,
        classification: str,
        source: str,
        schema_version: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    async def store_schema_diff(
        self,
        *,
        endpoint_id: str,
        endpoint_name: str,
        namespace: str,
        service_name: str,
        http_method: str,
        route_path: str,
        old_fingerprint: str,
        new_fingerprint: str,
        old_version: int,
        new_version: int,
        classification: str,
        diffs: list[dict[str, Any]],
        source: str,
    ) -> dict[str, Any]:
        ...

    async def store_validation_error(
        self,
        *,
        source: str,
        path: str,
        errors: list[dict[str, Any]],
        raw_body: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    async def store_replay_artifact(
        self,
        *,
        source: str,
        artifact_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    async def store_contract_review(
        self,
        *,
        endpoint_id: str,
        endpoint_name: str,
        provider: str,
        model_name: str | None,
        evidence_summary: str,
        consumer_impact: str,
        review: dict[str, Any],
        context: dict[str, Any],
        source: str,
    ) -> dict[str, Any]:
        ...

    async def get_payload_snapshot(self, document_id: str) -> dict[str, Any] | None:
        ...

    async def list_payload_snapshots(self, limit: int = 50) -> list[dict[str, Any]]:
        ...

    async def list_schema_diffs(self, limit: int = 50) -> list[dict[str, Any]]:
        ...

    async def list_validation_errors(self, limit: int = 50) -> list[dict[str, Any]]:
        ...

    async def list_replay_artifacts(self, limit: int = 50) -> list[dict[str, Any]]:
        ...

    async def list_contract_reviews(
        self, limit: int = 50, endpoint_id: str | None = None
    ) -> list[dict[str, Any]]:
        ...

    async def aclose(self) -> None:
        ...


class InMemoryDocumentStore:
    def __init__(self) -> None:
        self._collections: dict[str, dict[str, dict[str, Any]]] = {
            "payload_snapshots": {},
            "schema_diffs": {},
            "validation_errors": {},
            "replay_artifacts": {},
            "contract_reviews": {},
        }

    def _insert(self, collection: str, document: dict[str, Any]) -> dict[str, Any]:
        self._collections[collection][document["_id"]] = copy.deepcopy(document)
        return copy.deepcopy(document)

    def _list(self, collection: str, limit: int) -> list[dict[str, Any]]:
        docs = list(self._collections[collection].values())
        docs.sort(key=lambda item: item["created_at"], reverse=True)
        return [copy.deepcopy(doc) for doc in docs[:limit]]

    async def store_payload_snapshot(
        self,
        *,
        endpoint_id: str | None = None,
        namespace: str,
        service_name: str,
        http_method: str,
        route_path: str,
        payload: dict[str, Any],
        fingerprint: str,
        classification: str,
        source: str,
        schema_version: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._insert(
            "payload_snapshots",
            _document(
                "payload_snapshot",
                namespace=namespace,
                endpoint_id=endpoint_id,
                service_name=service_name,
                http_method=http_method,
                route_path=route_path,
                payload=payload,
                fingerprint=fingerprint,
                classification=classification,
                source=source,
                schema_version=schema_version,
                metadata=metadata or {},
            ),
        )

    async def store_schema_diff(
        self,
        *,
        endpoint_id: str,
        endpoint_name: str,
        namespace: str,
        service_name: str,
        http_method: str,
        route_path: str,
        old_fingerprint: str,
        new_fingerprint: str,
        old_version: int,
        new_version: int,
        classification: str,
        diffs: list[dict[str, Any]],
        source: str,
    ) -> dict[str, Any]:
        return self._insert(
            "schema_diffs",
            _document(
                "schema_diff",
                endpoint_id=endpoint_id,
                endpoint_name=endpoint_name,
                namespace=namespace,
                service_name=service_name,
                http_method=http_method,
                route_path=route_path,
                old_fingerprint=old_fingerprint,
                new_fingerprint=new_fingerprint,
                old_version=old_version,
                new_version=new_version,
                classification=classification,
                diffs=diffs,
                source=source,
            ),
        )

    async def store_validation_error(
        self,
        *,
        source: str,
        path: str,
        errors: list[dict[str, Any]],
        raw_body: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._insert(
            "validation_errors",
            _document(
                "validation_error",
                source=source,
                path=path,
                errors=errors,
                raw_body=raw_body,
                metadata=metadata or {},
            ),
        )

    async def store_replay_artifact(
        self,
        *,
        source: str,
        artifact_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._insert(
            "replay_artifacts",
            _document(
                "replay_artifact",
                source=source,
                artifact_type=artifact_type,
                payload=payload,
                metadata=metadata or {},
            ),
        )

    async def store_contract_review(
        self,
        *,
        endpoint_id: str,
        endpoint_name: str,
        provider: str,
        model_name: str | None,
        evidence_summary: str,
        consumer_impact: str,
        review: dict[str, Any],
        context: dict[str, Any],
        source: str,
    ) -> dict[str, Any]:
        return self._insert(
            "contract_reviews",
            _document(
                "contract_review",
                endpoint_id=endpoint_id,
                endpoint_name=endpoint_name,
                provider=provider,
                model_name=model_name,
                evidence_summary=evidence_summary,
                consumer_impact=consumer_impact,
                review=review,
                context=context,
                source=source,
            ),
        )

    async def get_payload_snapshot(self, document_id: str) -> dict[str, Any] | None:
        document = self._collections["payload_snapshots"].get(document_id)
        return copy.deepcopy(document) if document is not None else None

    async def list_payload_snapshots(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._list("payload_snapshots", limit)

    async def list_schema_diffs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._list("schema_diffs", limit)

    async def list_validation_errors(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._list("validation_errors", limit)

    async def list_replay_artifacts(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._list("replay_artifacts", limit)

    async def list_contract_reviews(
        self, limit: int = 50, endpoint_id: str | None = None
    ) -> list[dict[str, Any]]:
        docs = self._list("contract_reviews", limit * 4 if endpoint_id else limit)
        if endpoint_id is None:
            return docs[:limit]
        filtered = [doc for doc in docs if str(doc.get("endpoint_id")) == endpoint_id]
        return filtered[:limit]

    async def aclose(self) -> None:
        return None


class MongoDocumentStore:
    def __init__(
        self,
        uri: str | None,
        *,
        database: str = DEFAULT_DATABASE_NAME,
        client: AsyncMongoClient | None = None,
    ) -> None:
        if client is None:
            if not uri:
                raise ValueError("DOCUMENT_STORE_URI is required for MongoDocumentStore")
            client = AsyncMongoClient(uri)
        self._client = client
        self._db = client[database]

    async def _insert(self, collection: str, document: dict[str, Any]) -> dict[str, Any]:
        await self._db[collection].insert_one(document)
        return copy.deepcopy(document)

    async def _find(self, collection: str, document_id: str) -> dict[str, Any] | None:
        result = await self._db[collection].find_one({"_id": document_id})
        return copy.deepcopy(result) if result is not None else None

    async def _list(self, collection: str, limit: int) -> list[dict[str, Any]]:
        cursor = self._db[collection].find().sort("created_at", -1).limit(limit)
        documents = await cursor.to_list(length=limit)
        return [copy.deepcopy(doc) for doc in documents]

    async def store_payload_snapshot(
        self,
        *,
        endpoint_id: str | None = None,
        namespace: str,
        service_name: str,
        http_method: str,
        route_path: str,
        payload: dict[str, Any],
        fingerprint: str,
        classification: str,
        source: str,
        schema_version: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._insert(
            "payload_snapshots",
            _document(
                "payload_snapshot",
                namespace=namespace,
                endpoint_id=endpoint_id,
                service_name=service_name,
                http_method=http_method,
                route_path=route_path,
                payload=payload,
                fingerprint=fingerprint,
                classification=classification,
                source=source,
                schema_version=schema_version,
                metadata=metadata or {},
            ),
        )

    async def store_schema_diff(
        self,
        *,
        endpoint_id: str,
        endpoint_name: str,
        namespace: str,
        service_name: str,
        http_method: str,
        route_path: str,
        old_fingerprint: str,
        new_fingerprint: str,
        old_version: int,
        new_version: int,
        classification: str,
        diffs: list[dict[str, Any]],
        source: str,
    ) -> dict[str, Any]:
        return await self._insert(
            "schema_diffs",
            _document(
                "schema_diff",
                endpoint_id=endpoint_id,
                endpoint_name=endpoint_name,
                namespace=namespace,
                service_name=service_name,
                http_method=http_method,
                route_path=route_path,
                old_fingerprint=old_fingerprint,
                new_fingerprint=new_fingerprint,
                old_version=old_version,
                new_version=new_version,
                classification=classification,
                diffs=diffs,
                source=source,
            ),
        )

    async def store_validation_error(
        self,
        *,
        source: str,
        path: str,
        errors: list[dict[str, Any]],
        raw_body: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._insert(
            "validation_errors",
            _document(
                "validation_error",
                source=source,
                path=path,
                errors=errors,
                raw_body=raw_body,
                metadata=metadata or {},
            ),
        )

    async def store_replay_artifact(
        self,
        *,
        source: str,
        artifact_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._insert(
            "replay_artifacts",
            _document(
                "replay_artifact",
                source=source,
                artifact_type=artifact_type,
                payload=payload,
                metadata=metadata or {},
            ),
        )

    async def store_contract_review(
        self,
        *,
        endpoint_id: str,
        endpoint_name: str,
        provider: str,
        model_name: str | None,
        evidence_summary: str,
        consumer_impact: str,
        review: dict[str, Any],
        context: dict[str, Any],
        source: str,
    ) -> dict[str, Any]:
        return await self._insert(
            "contract_reviews",
            _document(
                "contract_review",
                endpoint_id=endpoint_id,
                endpoint_name=endpoint_name,
                provider=provider,
                model_name=model_name,
                evidence_summary=evidence_summary,
                consumer_impact=consumer_impact,
                review=review,
                context=context,
                source=source,
            ),
        )

    async def get_payload_snapshot(self, document_id: str) -> dict[str, Any] | None:
        return await self._find("payload_snapshots", document_id)

    async def list_payload_snapshots(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self._list("payload_snapshots", limit)

    async def list_schema_diffs(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self._list("schema_diffs", limit)

    async def list_validation_errors(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self._list("validation_errors", limit)

    async def list_replay_artifacts(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self._list("replay_artifacts", limit)

    async def list_contract_reviews(
        self, limit: int = 50, endpoint_id: str | None = None
    ) -> list[dict[str, Any]]:
        if endpoint_id is None:
            return await self._list("contract_reviews", limit)
        documents = await self._list("contract_reviews", max(limit * 4, limit))
        filtered = [doc for doc in documents if str(doc.get("endpoint_id")) == endpoint_id]
        return filtered[:limit]

    async def aclose(self) -> None:
        close = getattr(self._client, "close", None)
        if close is None:
            return None
        result = close()
        if inspect.isawaitable(result):
            await result
        return None


def build_document_store() -> DocumentStore:
    backend = os.getenv("DOCUMENT_STORE_BACKEND", "memory").strip().lower()
    if backend in {"memory", "noop", "none"}:
        return InMemoryDocumentStore()
    if backend in {"mongo", "cosmos", "cosmos_mongo"}:
        uri = os.getenv("DOCUMENT_STORE_URI")
        database = os.getenv("DOCUMENT_STORE_DATABASE", DEFAULT_DATABASE_NAME)
        if not uri:
            raise RuntimeError("DOCUMENT_STORE_URI is required when DOCUMENT_STORE_BACKEND uses Mongo")
        return MongoDocumentStore(uri, database=database)
    raise ValueError(f"Unsupported DOCUMENT_STORE_BACKEND: {backend}")
