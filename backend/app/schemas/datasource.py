from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DataSourceType = Literal["sqlite", "excel", "csv"]


class DataSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: DataSourceType
    path: str


class DataSourceOut(BaseModel):
    id: str
    name: str
    source_type: DataSourceType
    path: str
    status: str
    checksum: str | None
    last_scanned_at: datetime | None
    error: str | None = None
    profile: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class ColumnOut(BaseModel):
    original_name: str
    normalized_name: str
    data_type: str
    nullable: bool | None
    null_count: int | None
    sample_values: list[Any] = Field(default_factory=list)
    ordinal: int

    model_config = {"from_attributes": True}


class TableOut(BaseModel):
    id: str
    data_source_id: str
    database_name: str | None
    original_name: str
    canonical_name: str
    kind: str
    row_count: int | None
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)
    columns: list[ColumnOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class RelationshipOut(BaseModel):
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    confidence: float
    evidence: str

    model_config = {"from_attributes": True}


class SchemaOut(BaseModel):
    data_sources: list[DataSourceOut]
    tables: list[TableOut]
    relationships: list[RelationshipOut]


class PreviewTableOption(BaseModel):
    canonical_name: str
    original_name: str
    row_count: int | None = None


class TablePreviewOut(BaseModel):
    data_source_id: str
    table: str
    original_name: str
    page: int
    page_size: int
    total_rows: int | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    tables: list[PreviewTableOption] = Field(default_factory=list)
