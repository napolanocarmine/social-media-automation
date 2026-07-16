from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from social_automation.api.routers import (
    automation,
    batches,
    calendar,
    config,
    cron,
    dashboard,
    dispatch,
    drive,
    health,
    images,
    media,
    oauth_google,
    plans,
)

API_V1_PREFIX = "/api/v1"
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Story Social API",
        version="0.1.0",
        docs_url=f"{API_V1_PREFIX}/docs",
        openapi_url=f"{API_V1_PREFIX}/openapi.json",
    )

    cors_origins = os.getenv(
        "API_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix=API_V1_PREFIX)
    app.include_router(dashboard.router, prefix=API_V1_PREFIX)
    app.include_router(config.router, prefix=API_V1_PREFIX)
    app.include_router(drive.router, prefix=API_V1_PREFIX)
    app.include_router(images.router, prefix=API_V1_PREFIX)
    app.include_router(media.router, prefix=API_V1_PREFIX)
    app.include_router(batches.router, prefix=API_V1_PREFIX)
    app.include_router(plans.router, prefix=API_V1_PREFIX)
    app.include_router(calendar.router, prefix=API_V1_PREFIX)
    app.include_router(dispatch.router, prefix=API_V1_PREFIX)
    app.include_router(automation.router, prefix=API_V1_PREFIX)
    app.include_router(cron.router, prefix="/api")
    app.include_router(oauth_google.router, prefix=API_V1_PREFIX)

    @app.get("/api/health")
    def legacy_health():
        """Alias compatibile con piano migrazione (`GET /api/health`)."""
        return {"status": "ok", "service": "social-media-automation-api"}

    @app.exception_handler(RuntimeError)
    async def runtime_error_handler(_request: Request, exc: RuntimeError) -> JSONResponse:
        message = str(exc).strip() or exc.__class__.__name__
        logger.exception("RuntimeError: %s", message)
        return JSONResponse(status_code=502, content={"detail": message})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        message = str(exc).strip() or exc.__class__.__name__
        logger.exception("Unhandled exception: %s", message)
        return JSONResponse(status_code=500, content={"detail": message})

    return app


app = create_app()
