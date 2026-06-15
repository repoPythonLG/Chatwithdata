from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import admin_user
from app.datasources.catalog import DataSourceCatalog
from app.db.models import User
from app.db.session import get_session
from app.schemas.datasource import SchemaOut

router = APIRouter(prefix="/schema", tags=["schema"])


@router.get("", response_model=SchemaOut)
async def get_schema(
    source_id: list[str] | None = Query(default=None),
    _admin: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
):
    return await DataSourceCatalog(session).get_schema(source_id)
