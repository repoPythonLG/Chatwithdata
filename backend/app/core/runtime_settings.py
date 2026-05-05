from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import AppSetting
from app.schemas.settings import SettingsOut, SettingsUpdate

ALLOWED_RUNTIME_KEYS = {
    "llm_base_url",
    "openai_api_key",
    "model_name",
    "model_temperature",
    "model_max_tokens",
    "model_timeout_seconds",
    "qwen_command",
    "qwen_model",
    "qwen_timeout_seconds",
    "qwen_auth_type",
    "qwen_approval_mode",
    "qwen_use_sandbox",
}


class RuntimeSettingsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.base = get_settings()

    async def get_overrides(self) -> dict[str, Any]:
        rows = (await self.session.execute(select(AppSetting))).scalars().all()
        return {row.key: row.value for row in rows}

    async def get_effective(self) -> dict[str, Any]:
        overrides = await self.get_overrides()
        return {
            "app_name": self.base.app_name,
            "environment": self.base.environment,
            "llm_base_url": overrides.get("llm_base_url", self.base.llm_base_url),
            "openai_api_key": overrides.get("openai_api_key", self.base.openai_api_key),
            "openai_api_key_configured": bool(
                overrides.get("openai_api_key") or self.base.openai_api_key
            ),
            "model_name": overrides.get("model_name", self.base.model_name),
            "model_temperature": overrides.get("model_temperature", self.base.model_temperature),
            "model_max_tokens": overrides.get("model_max_tokens", self.base.model_max_tokens),
            "model_timeout_seconds": overrides.get(
                "model_timeout_seconds", self.base.model_timeout_seconds
            ),
            "sql_result_row_limit": self.base.sql_result_row_limit,
            "python_timeout_seconds": self.base.python_timeout_seconds,
            "qwen_command": overrides.get("qwen_command", self.base.qwen_command),
            "qwen_model": overrides.get("qwen_model", self.base.qwen_model),
            "qwen_timeout_seconds": overrides.get(
                "qwen_timeout_seconds", self.base.qwen_timeout_seconds
            ),
            "qwen_auth_type": overrides.get("qwen_auth_type", self.base.qwen_auth_type),
            "qwen_approval_mode": overrides.get(
                "qwen_approval_mode", self.base.qwen_approval_mode
            ),
            "qwen_use_sandbox": overrides.get("qwen_use_sandbox", self.base.qwen_use_sandbox),
        }

    async def get_out(self) -> SettingsOut:
        values = await self.get_effective()
        values.pop("openai_api_key", None)
        return SettingsOut(**values)

    async def update(self, payload: SettingsUpdate) -> SettingsOut:
        values = payload.model_dump(exclude_unset=True)
        for key, value in values.items():
            if key not in ALLOWED_RUNTIME_KEYS:
                continue
            row = await self.session.get(AppSetting, key)
            if row is None:
                row = AppSetting(key=key, value=value)
                self.session.add(row)
            else:
                row.value = value
        await self.session.commit()
        return await self.get_out()


def settings_from_effective(values: dict[str, Any], base: Settings | None = None) -> Settings:
    """Create an immutable settings-like object for services that need runtime overrides."""

    base_settings = base or get_settings()
    data = base_settings.model_dump()
    data["vllm_base_url"] = values.get("llm_base_url", base_settings.llm_base_url)
    data["openai_api_base"] = None
    data["openai_api_key"] = values.get("openai_api_key", base_settings.openai_api_key)
    data["model_name"] = values.get("model_name", base_settings.model_name)
    data["model_temperature"] = values.get("model_temperature", base_settings.model_temperature)
    data["model_max_tokens"] = values.get("model_max_tokens", base_settings.model_max_tokens)
    data["model_timeout_seconds"] = values.get(
        "model_timeout_seconds", base_settings.model_timeout_seconds
    )
    data["qwen_command"] = values.get("qwen_command", base_settings.qwen_command)
    data["qwen_model"] = values.get("qwen_model", base_settings.qwen_model)
    data["qwen_timeout_seconds"] = values.get(
        "qwen_timeout_seconds", base_settings.qwen_timeout_seconds
    )
    data["qwen_auth_type"] = values.get("qwen_auth_type", base_settings.qwen_auth_type)
    data["qwen_approval_mode"] = values.get(
        "qwen_approval_mode", base_settings.qwen_approval_mode
    )
    data["qwen_use_sandbox"] = values.get("qwen_use_sandbox", base_settings.qwen_use_sandbox)
    return Settings(**data)
