from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _advisory_key(name: str) -> int:
    """Convert a string label to a stable 64-bit advisory lock key."""
    digest = hashlib.sha256(name.encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@asynccontextmanager
async def advisory_lock(
    session: AsyncSession, name: str
) -> AsyncGenerator[bool, None]:
    """Try to take a Postgres advisory lock for the current transaction (non-blocking).

    Yields True if the lock was acquired, False if another transaction holds it.
    Postgres releases the lock on commit or rollback. A session-level lock would have
    to be released on the same pooled connection, which is not guaranteed after a commit.
    """
    key = _advisory_key(name)
    result = await session.execute(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
    )
    yield result.scalar()
