import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("driftgate")


def create_app() -> FastAPI:
    app = FastAPI(
        title="DRIFTGATE Scheduled Monitor",
        version=__version__,
        description="Scheduled API contract monitor and changelog service",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    from app.api import (
        changelog,
        diffs,
        endpoints,
        health,
        monitor,
        snapshots,
    )

    app.include_router(health.router)
    app.include_router(endpoints.router)
    app.include_router(snapshots.router)
    app.include_router(diffs.router)
    app.include_router(monitor.router)
    app.include_router(changelog.router)

    log.info("DRIFTGATE monitor started, cors=%s", settings.cors_origins)
    return app


app = create_app()
