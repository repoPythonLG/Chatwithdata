from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.security import resolve_local_path
from app.datasources.csv_scanner import CSV_EXTENSIONS, CSVScanner
from app.datasources.excel_scanner import EXCEL_EXTENSIONS, ExcelScanner
from app.datasources.relationships import infer_relationships
from app.datasources.sqlite_scanner import SQLiteScanner
from app.db.models import (
    ColumnMetadata,
    DataSource,
    RelationshipMetadata,
    TableMetadata,
)
from app.schemas.datasource import DataSourceCreate, SchemaOut


class DataSourceCatalog:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    async def list_sources(self) -> list[DataSource]:
        result = await self.session.execute(select(DataSource).order_by(DataSource.created_at))
        return list(result.scalars().all())

    async def create_source(self, payload: DataSourceCreate) -> DataSource:
        path = resolve_local_path(payload.path, self.settings.allowed_data_roots)
        self._validate_source_type(payload.source_type, path)

        source = DataSource(
            name=payload.name,
            source_type=payload.source_type,
            path=str(path),
            status="pending",
        )
        self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)

        await self.scan_source(source.id, force=True)
        refreshed = await self.session.get(DataSource, source.id)
        if refreshed is None:
            raise RuntimeError("Data source disappeared after scan")
        return refreshed

    async def delete_source(self, source_id: str) -> None:
        source = await self.session.get(DataSource, source_id)
        if source is None:
            return
        await self.session.delete(source)
        await self.session.commit()
        await self.rebuild_relationships()

    async def rescan(
        self, source_ids: list[str] | None = None, force: bool = False
    ) -> list[DataSource]:
        query = select(DataSource)
        if source_ids:
            query = query.where(DataSource.id.in_(source_ids))
        sources = list((await self.session.execute(query)).scalars().all())
        for source in sources:
            await self.scan_source(source.id, force=force)
        return await self.list_sources()

    async def scan_source(self, source_id: str, *, force: bool = False) -> None:
        source = await self.session.get(DataSource, source_id)
        if source is None:
            raise ValueError(f"Unknown data source: {source_id}")

        path = resolve_local_path(source.path, self.settings.allowed_data_roots)
        scanner = self._scanner_for_source(source.source_type)

        source.status = "scanning"
        source.error = None
        await self.session.commit()

        try:
            scan = await asyncio.to_thread(scanner.scan, source.id, source.name, path)
            if not force and source.checksum and source.checksum == scan["checksum"]:
                source.status = "active"
                source.last_scanned_at = datetime.utcnow()
                await self.session.commit()
                return

            await self.session.execute(
                delete(TableMetadata).where(TableMetadata.data_source_id == source.id)
            )
            await self.session.flush()
            for table_payload in scan["tables"]:
                table = TableMetadata(
                    data_source_id=source.id,
                    database_name=table_payload.get("database_name"),
                    original_name=table_payload["original_name"],
                    canonical_name=table_payload["canonical_name"],
                    kind=table_payload["kind"],
                    row_count=table_payload.get("row_count"),
                    sample_rows=table_payload.get("sample_rows") or [],
                    profile=table_payload.get("profile") or {},
                )
                self.session.add(table)
                await self.session.flush()
                for column_payload in table_payload["columns"]:
                    self.session.add(
                        ColumnMetadata(
                            table_id=table.id,
                            original_name=column_payload["original_name"],
                            normalized_name=column_payload["normalized_name"],
                            data_type=column_payload["data_type"],
                            nullable=column_payload.get("nullable"),
                            null_count=column_payload.get("null_count"),
                            sample_values=column_payload.get("sample_values") or [],
                            ordinal=column_payload["ordinal"],
                            profile=column_payload.get("profile") or {},
                        )
                    )

            source.checksum = scan["checksum"]
            source.profile = {
                **(scan.get("profile") or {}),
                "declared_relationships": scan.get("relationships") or [],
            }
            source.status = "active"
            source.error = None
            source.last_scanned_at = datetime.utcnow()
            await self.session.commit()

            await self.rebuild_relationships()
        except Exception as exc:
            source.status = "error"
            source.error = str(exc)
            source.last_scanned_at = datetime.utcnow()
            await self.session.commit()
            raise

    async def rebuild_relationships(self) -> None:
        await self.session.execute(delete(RelationshipMetadata))
        tables = await self._load_tables()
        sources = list((await self.session.execute(select(DataSource))).scalars().all())
        declared = [
            rel
            for source in sources
            for rel in (source.profile or {}).get("declared_relationships", [])
        ]
        relationships = declared + infer_relationships(tables)
        seen: set[tuple[str, str, str, str]] = set()
        for item in relationships:
            key = (
                str(item["left_table"]),
                str(item["left_column"]),
                str(item["right_table"]),
                str(item["right_column"]),
            )
            if key in seen:
                continue
            seen.add(key)
            self.session.add(
                RelationshipMetadata(
                    left_table=key[0],
                    left_column=key[1],
                    right_table=key[2],
                    right_column=key[3],
                    confidence=float(item.get("confidence", 0.5)),
                    evidence=str(item.get("evidence", "")),
                )
            )
        await self.session.commit()

    async def get_schema(self, selected_source_ids: list[str] | None = None) -> SchemaOut:
        source_query = select(DataSource).order_by(DataSource.name)
        table_query = (
            select(TableMetadata)
            .options(selectinload(TableMetadata.columns))
            .order_by(TableMetadata.canonical_name)
        )
        if selected_source_ids:
            source_query = source_query.where(DataSource.id.in_(selected_source_ids))
            table_query = table_query.where(TableMetadata.data_source_id.in_(selected_source_ids))

        sources = list((await self.session.execute(source_query)).scalars().all())
        tables = list((await self.session.execute(table_query)).scalars().unique().all())
        rels = list((await self.session.execute(select(RelationshipMetadata))).scalars().all())
        allowed_tables = {table.canonical_name for table in tables}
        rels = [
            rel
            for rel in rels
            if rel.left_table in allowed_tables and rel.right_table in allowed_tables
        ]
        return SchemaOut(data_sources=sources, tables=tables, relationships=rels)

    async def compact_schema_text(self, selected_source_ids: list[str] | None = None) -> str:
        schema = await self.get_schema(selected_source_ids)
        lines: list[str] = []
        for source in schema.data_sources:
            lines.append(f"Source {source.name} ({source.source_type}, id={source.id})")
            source_tables = [table for table in schema.tables if table.data_source_id == source.id]
            for table in source_tables:
                columns = ", ".join(
                    f"{col.normalized_name}:{col.data_type}" for col in table.columns
                )
                lines.append(
                    f"- {table.canonical_name} [{table.kind}, rows={table.row_count}]: {columns}"
                )
                if table.sample_rows:
                    lines.append(f"  sample_rows={table.sample_rows[:2]}")
        if schema.relationships:
            lines.append("Relationships:")
            for rel in schema.relationships:
                lines.append(
                    f"- {rel.left_table}.{rel.left_column} -> "
                    f"{rel.right_table}.{rel.right_column} "
                    f"(confidence={rel.confidence:.2f}, {rel.evidence})"
                )
        return "\n".join(lines) if lines else "No data sources are configured."

    async def table_column_map(
        self, selected_source_ids: list[str] | None = None
    ) -> dict[str, set[str]]:
        tables = await self._load_tables(selected_source_ids)
        return {
            table.canonical_name: {column.normalized_name for column in table.columns}
            for table in tables
        }

    async def _load_tables(
        self, selected_source_ids: list[str] | None = None
    ) -> list[TableMetadata]:
        query = (
            select(TableMetadata)
            .options(selectinload(TableMetadata.columns))
            .order_by(TableMetadata.canonical_name)
        )
        if selected_source_ids:
            query = query.where(TableMetadata.data_source_id.in_(selected_source_ids))
        result = await self.session.execute(query)
        return list(result.scalars().unique().all())

    @staticmethod
    def _scanner_for_source(source_type: str) -> CSVScanner | ExcelScanner | SQLiteScanner:
        if source_type == "csv":
            return CSVScanner(get_settings())
        if source_type == "excel":
            return ExcelScanner(get_settings())
        return SQLiteScanner(get_settings())

    @staticmethod
    def _validate_source_type(source_type: str, path: Path) -> None:
        if source_type == "csv" and path.suffix.lower() not in CSV_EXTENSIONS:
            raise ValueError("CSV data sources must be .csv or .tsv files")
        if source_type == "excel" and path.suffix.lower() not in EXCEL_EXTENSIONS:
            raise ValueError("Excel data sources must be .xlsx, .xlsm, or .xls files")
        if source_type == "sqlite" and path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
            raise ValueError("SQLite data sources must be .db, .sqlite, or .sqlite3 files")
