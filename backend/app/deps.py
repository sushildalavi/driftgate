from __future__ import annotations

import secrets
from typing import Annotated, AsyncGenerator

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session

# ── DB session ─────────────────────────────────────────────────────────────────

DbSession = Annotated[AsyncSession, Depends(get_session)]


# ── Admin auth ─────────────────────────────────────────────────────────────────

def require_admin(
    x_driftgate_admin_secret: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.admin_secret
    provided = x_driftgate_admin_secret or ""
    if not expected or not secrets.compare_digest(provided, expected):
        raise HTTPException(401, detail="Invalid or missing admin secret")
