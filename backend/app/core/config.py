from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings.

    Runtime model knobs can also be overridden through the `/settings` API and are
    merged by the settings service. Environment values remain the secure default.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Corporate Data Chat"
    environment: str = "local"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    app_data_dir: Path = Field(default=Path(".data"))
    metadata_db_path: Path = Field(default=Path(".data/app_metadata.db"))
    python_work_dir: Path = Field(default=Path(".data/python-work"))

    allowed_data_roots: list[Path] = Field(default_factory=list)

    vllm_base_url: str = Field(default="http://localhost:8000/v1")
    openai_api_base: str | None = None
    openai_api_key: str = Field(default="local-key")
    model_name: str = Field(default="qwen3-coder-next")
    model_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    model_max_tokens: int = Field(default=4096, ge=256, le=32768)
    model_timeout_seconds: float = Field(default=120.0, ge=5.0)
    model_retries: int = Field(default=2, ge=0, le=5)

    sql_timeout_seconds: float = Field(default=30.0, ge=1.0)
    sql_result_row_limit: int = Field(default=1000, ge=1, le=100000)
    sql_preview_row_limit: int = Field(default=100, ge=1, le=1000)

    python_timeout_seconds: float = Field(default=20.0, ge=1.0)
    python_max_code_chars: int = Field(default=12000, ge=1000, le=100000)

    metadata_sample_rows: int = Field(default=5, ge=1, le=50)
    metadata_profile_value_limit: int = Field(default=20, ge=1, le=100)
    metadata_cache_seconds: int = Field(default=120, ge=0)

    @field_validator("allowed_data_roots", mode="before")
    @classmethod
    def parse_roots(cls, value: Any) -> list[Path]:
        if value in (None, "", []):
            return []
        if isinstance(value, str):
            return [Path(item.strip()) for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def llm_base_url(self) -> str:
        return self.openai_api_base or self.vllm_base_url

    def ensure_directories(self) -> None:
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.python_work_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
