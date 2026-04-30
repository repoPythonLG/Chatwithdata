from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.routes import chat, datasources, health, schema, settings
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import init_db

settings_obj = get_settings()
configure_logging(settings_obj.log_level)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings_obj.app_name,
        version="0.1.0",
        default_response_class=ORJSONResponse,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings_obj.cors_origins,
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$"
        if settings_obj.environment == "local"
        else None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def on_startup() -> None:
        await init_db()
        logger.info("Application metadata database initialized")

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        return ORJSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(health.router)
    app.include_router(settings.router)
    app.include_router(datasources.router)
    app.include_router(schema.router)
    app.include_router(chat.router)
    return app


app = create_app()
