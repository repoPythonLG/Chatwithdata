from __future__ import annotations

from pydantic import BaseModel, Field


class SettingsOut(BaseModel):
    app_name: str
    environment: str
    llm_base_url: str
    openai_api_key_configured: bool = False
    model_name: str
    model_temperature: float
    model_max_tokens: int
    model_timeout_seconds: float
    sql_result_row_limit: int
    python_timeout_seconds: float
    qwen_command: str
    qwen_model: str | None = None
    qwen_timeout_seconds: float
    qwen_auth_type: str | None = None
    qwen_approval_mode: str
    qwen_use_sandbox: bool


class SettingsUpdate(BaseModel):
    llm_base_url: str | None = None
    openai_api_key: str | None = Field(default=None, min_length=1)
    model_name: str | None = None
    model_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    model_max_tokens: int | None = Field(default=None, ge=256, le=32768)
    model_timeout_seconds: float | None = Field(default=None, ge=5.0)
    qwen_command: str | None = Field(default=None, min_length=1)
    qwen_model: str | None = None
    qwen_timeout_seconds: float | None = Field(default=None, ge=10.0)
    qwen_auth_type: str | None = None
    qwen_approval_mode: str | None = None
    qwen_use_sandbox: bool | None = None
