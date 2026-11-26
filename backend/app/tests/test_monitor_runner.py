import asyncio
import uuid

from app.core.fetcher import FetchResult
from app.models import ApiEndpoint
from app.workers import monitor_runner


class _NoPriorSnapshot:
    def scalar_one_or_none(self):
        return None


class _ExclusiveSession:
    """Stands in for AsyncSession and fails if two tasks use it at once."""

    def __init__(self) -> None:
        self.busy = False

    async def _use(self):
        assert not self.busy, "session used concurrently"
        self.busy = True
        await asyncio.sleep(0)
        self.busy = False

    def add(self, _row) -> None:
        pass

    async def flush(self) -> None:
        await self._use()

    async def execute(self, _statement):
        await self._use()
        return _NoPriorSnapshot()


async def test_endpoints_are_stored_without_sharing_the_session(monkeypatch):
    async def fake_fetch(**_kwargs):
        return FetchResult(status_code=200, response_time_ms=1, response_size_bytes=8, body={"id": 1})

    monkeypatch.setattr(monitor_runner, "fetch_endpoint", fake_fetch)
    endpoints = [
        ApiEndpoint(id=uuid.uuid4(), name=f"api-{i}", url="http://example.invalid", method="GET", headers_json={})
        for i in range(4)
    ]

    results = await monitor_runner._process_endpoints(_ExclusiveSession(), endpoints, uuid.uuid4())

    assert [r.snapshot_created for r in results] == [True] * 4
