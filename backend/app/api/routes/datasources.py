from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import admin_user, current_user
from app.core.config import get_settings
from app.core.security import safe_filename
from app.datasources.catalog import DataSourceCatalog
from app.datasources.query_engine import QueryEngine
from app.db.models import User
from app.db.session import get_session
from app.schemas.datasource import DataSourceCreate, DataSourceOut, TablePreviewOut

router = APIRouter(prefix="/datasources", tags=["datasources"])


class RescanRequest(BaseModel):
    source_ids: list[str] | None = None
    force: bool = False


SOURCE_TYPE_BY_EXTENSION = {
    ".csv": "csv",
    ".db": "sqlite",
    ".sqlite": "sqlite",
    ".sqlite3": "sqlite",
    ".tsv": "csv",
    ".xls": "excel",
    ".xlsm": "excel",
    ".xlsx": "excel",
}


@router.get("", response_model=list[DataSourceOut])
async def list_datasources(
    _admin: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
):
    return await DataSourceCatalog(session).list_sources()


@router.post("", response_model=DataSourceOut)
async def create_datasource(
    payload: DataSourceCreate,
    _admin: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await DataSourceCatalog(session).create_source(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/upload", response_model=DataSourceOut)
async def upload_datasource(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    _admin: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
):
    original_name = file.filename or "uploaded-data"
    extension = Path(original_name).suffix.lower()
    source_type = SOURCE_TYPE_BY_EXTENSION.get(extension)
    if source_type is None:
        supported = ", ".join(sorted(SOURCE_TYPE_BY_EXTENSION))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported extensions: {supported}",
        )

    settings = get_settings()
    upload_dir = settings.app_data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = upload_dir / f"{uuid.uuid4().hex}_{safe_filename(original_name)}"

    max_bytes = 250 * 1024 * 1024
    bytes_written = 0
    try:
        with destination.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    destination.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail="File is too large. Maximum upload size is 250 MB.",
                    )
                output.write(chunk)

        display_name = name.strip() if name and name.strip() else Path(original_name).stem
        payload = DataSourceCreate(
            name=display_name,
            source_type=source_type,
            path=str(destination.resolve()),
        )
        return await DataSourceCatalog(session).create_source(payload)
    except HTTPException:
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()


@router.delete("/{source_id}", status_code=204)
async def delete_datasource(
    source_id: str,
    _admin: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
):
    await DataSourceCatalog(session).delete_source(source_id)


@router.post("/rescan", response_model=list[DataSourceOut])
async def rescan_datasources(
    payload: RescanRequest | None = None,
    _admin: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        payload = payload or RescanRequest()
        return await DataSourceCatalog(session).rescan(payload.source_ids, force=payload.force)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{source_id}/preview", response_model=TablePreviewOut)
async def preview_datasource_table(
    source_id: str,
    table: str | None = None,
    page: int = 1,
    page_size: int = 50,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        preview = await QueryEngine(session).preview_table(
            source_id=source_id,
            table_name=table,
            page=page,
            page_size=page_size,
        )
        return TablePreviewOut(**preview.__dict__)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
