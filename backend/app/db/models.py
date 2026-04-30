from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def new_id() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)


class DataSource(Base, TimestampMixin):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    tables: Mapped[list[TableMetadata]] = relationship(
        back_populates="data_source", cascade="all, delete-orphan"
    )


class TableMetadata(Base, TimestampMixin):
    __tablename__ = "table_metadata"
    __table_args__ = (
        UniqueConstraint("data_source_id", "canonical_name", name="uq_table_source_canonical"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    data_source_id: Mapped[str] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    database_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    data_source: Mapped[DataSource] = relationship(back_populates="tables")
    columns: Mapped[list[ColumnMetadata]] = relationship(
        back_populates="table", cascade="all, delete-orphan", order_by="ColumnMetadata.ordinal"
    )


class ColumnMetadata(Base, TimestampMixin):
    __tablename__ = "column_metadata"
    __table_args__ = (
        UniqueConstraint("table_id", "normalized_name", name="uq_column_table_normalized"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    table_id: Mapped[str] = mapped_column(
        ForeignKey("table_metadata.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(128), nullable=False)
    nullable: Mapped[bool | None] = mapped_column(nullable=True)
    null_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_values: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    table: Mapped[TableMetadata] = relationship(back_populates="columns")


class RelationshipMetadata(Base, TimestampMixin):
    __tablename__ = "relationship_metadata"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    left_table: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    left_column: Mapped[str] = mapped_column(String(255), nullable=False)
    right_table: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    right_column: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.5)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New conversation")

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
