from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, chat, contracts, datasources, health, schema, settings
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

    api_routers = [
        health.router,
        auth.auth_router,
        auth.users_router,
        settings.router,
        contracts.router,
        datasources.router,
        schema.router,
        chat.router,
    ]
    for router in api_routers:
        app.include_router(router)
        app.include_router(router, prefix="/api")

    _mount_static_frontend(app)
    return app


def _mount_static_frontend(app: FastAPI) -> None:
    dist_dir = settings_obj.frontend_dist_dir
    if not dist_dir.is_absolute():
        dist_dir = Path.cwd() / dist_dir
    dist_dir = dist_dir.resolve()
    index_path = dist_dir / "index.html"
    assets_dir = dist_dir / "assets"
    if not index_path.exists():
        logger.info("Static frontend not mounted; missing %s", index_path)
        return
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/healthz", include_in_schema=False)
    async def static_healthz():
        return {"status": "ok", "service": settings_obj.app_name}

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        candidate = (dist_dir / full_path).resolve()
        if candidate.is_file() and (
            candidate == dist_dir or str(candidate).startswith(f"{dist_dir}/")
        ):
            return FileResponse(candidate)
        return FileResponse(index_path)


app = create_app()
