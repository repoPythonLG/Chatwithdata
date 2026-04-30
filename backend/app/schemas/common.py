from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    detail: str


class StatusEvent(BaseModel):
    step: str
    status: Literal["pending", "running", "completed", "warning", "error"]
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TableArtifact(BaseModel):
    type: Literal["table"] = "table"
    title: str = "Result table"
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    truncated: bool = False


class ChartArtifact(BaseModel):
    type: Literal["chart"] = "chart"
    title: str = "Chart"
    spec: dict[str, Any] = Field(default_factory=dict)


Artifact = TableArtifact | ChartArtifact
