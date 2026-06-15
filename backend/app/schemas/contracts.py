from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.datasource import DataSourceOut


class ContractDocumentOut(BaseModel):
    id: str
    name: str
    filename: str
    path: str
    extracted_text_path: str | None = None
    content_type: str | None = None
    size_bytes: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ContractWorkspaceOut(BaseModel):
    database: DataSourceOut | None = None
    documents: list[ContractDocumentOut] = Field(default_factory=list)
