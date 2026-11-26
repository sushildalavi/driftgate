import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.api import changelog as changelog_api
from app.core import changelog as changelog_core
from app.schemas import ChangelogGenerateRequest


class _Session:
    def __init__(self, snapshot) -> None:
        self.snapshot = snapshot
        self.commits = 0

    async def get(self, _model, _key):
        return self.snapshot

    async def execute(self, _statement):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [object()]))

    async def commit(self) -> None:
        self.commits += 1


async def test_generated_changelog_is_committed(monkeypatch):
    snapshot = SimpleNamespace(id=uuid.uuid4(), normalized_schema_json=[{"path": "id"}])
    stored = SimpleNamespace(
        id=uuid.uuid4(),
        endpoint_id=uuid.uuid4(),
        snapshot_id=snapshot.id,
        diff_ids=[],
        diff_set_hash="hash",
        generated_text="## Safe",
        model_name=None,
        created_at=datetime.now(timezone.utc),
    )

    async def fake_generate(_db, _snapshot, _rows):
        return stored

    monkeypatch.setattr(changelog_core, "generate_changelog", fake_generate)
    session = _Session(snapshot)

    result = await changelog_api.generate_changelog(
        ChangelogGenerateRequest(snapshot_id=snapshot.id), session
    )

    assert result.id == stored.id
    assert session.commits == 1
