"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from marginos import __version__
from marginos.core.config import get_settings
from marginos.core.events import router as events_router
from marginos.core.logging import configure_logging
from marginos.core.models_registry import import_all_models

log = logging.getLogger("marginos")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    missing = settings.missing_required()
    if missing and settings.app_env == "production":
        raise RuntimeError(f"missing required settings: {', '.join(missing)}")
    if missing:
        log.warning("integrations not fully configured, missing: %s", ", ".join(missing))
    log.info("MarginOS API %s starting (env=%s)", __version__, settings.app_env)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    import_all_models()
    app = FastAPI(title="MarginOS API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_base_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    app.include_router(events_router)
    return app


app = create_app()
