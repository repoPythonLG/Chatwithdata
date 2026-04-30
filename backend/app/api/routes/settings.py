from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.runtime_settings import RuntimeSettingsService
from app.db.session import get_session
from app.schemas.settings import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
async def get_settings(session: AsyncSession = Depends(get_session)):
    return await RuntimeSettingsService(session).get_out()


@router.post("", response_model=SettingsOut)
async def update_settings(payload: SettingsUpdate, session: AsyncSession = Depends(get_session)):
    return await RuntimeSettingsService(session).update(payload)
