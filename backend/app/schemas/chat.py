from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import Artifact, StatusEvent


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    conversation_id: str | None = None
    selected_data_sources: list[str] | None = None
    engine: Literal["standard", "qwen_cli"] = "qwen_cli"
    stream: bool = False


class SourceReference(BaseModel):
    data_source_id: str | None = None
    data_source_name: str | None = None
    table: str | None = None
    columns: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str | None = None
    answer: str
    reasoning_summary: str = ""
    sql_query: str | None = None
    python_code: str | None = None
    qwen_output: str | None = None
    qwen_workspace: str | None = None
    artifacts: list[Artifact] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"
    status_events: list[StatusEvent] = Field(default_factory=list)


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}
