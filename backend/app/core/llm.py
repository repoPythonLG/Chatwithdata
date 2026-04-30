from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Small abstraction for OpenAI-compatible Qwen/vLLM endpoints."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.client = AsyncOpenAI(
            base_url=self.settings.llm_base_url,
            api_key=self.settings.openai_api_key,
            timeout=self.settings.model_timeout_seconds,
            max_retries=0,
        )

    async def health(self) -> dict[str, Any]:
        try:
            models = await self.client.models.list()
            ids = [model.id for model in models.data]
            return {
                "status": "ok",
                "base_url": self.settings.llm_base_url,
                "model_name": self.settings.model_name,
                "available_models": ids,
                "configured_model_available": self.settings.model_name in ids if ids else None,
            }
        except Exception as exc:  # pragma: no cover - depends on external endpoint
            logger.warning("Model health check failed: %s", exc)
            return {
                "status": "unavailable",
                "base_url": self.settings.llm_base_url,
                "model_name": self.settings.model_name,
                "error": str(exc),
            }

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def complete_text(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        response = await self.client.chat.completions.create(
            model=self.settings.model_name,
            messages=messages,
            temperature=self.settings.model_temperature if temperature is None else temperature,
            max_tokens=max_tokens or self.settings.model_max_tokens,
        )
        return response.choices[0].message.content or ""

    async def complete_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        text = await self.complete_text(
            messages,
            temperature=temperature,
            max_tokens=max_tokens or min(self.settings.model_max_tokens, 2048),
        )
        return self._parse_json_object(text)

    async def stream_text(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        stream = await self.client.chat.completions.create(
            model=self.settings.model_name,
            messages=messages,
            temperature=self.settings.model_temperature if temperature is None else temperature,
            max_tokens=max_tokens or self.settings.model_max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError(f"Model did not return a JSON object: {text[:500]}")
        return json.loads(stripped[start : end + 1])
