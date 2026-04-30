from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import safe_filename
from app.datasources.csv_scanner import read_csv_file
from app.datasources.excel_scanner import read_excel_sheet
from app.datasources.profiling import json_safe
from app.datasources.sqlite_scanner import quote_sqlite_identifier
from app.datasources.table_aliases import unique_table_aliases
from app.db.models import DataSource, TableMetadata

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    duration_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)


class QueryEngine:
    """Unified read-only analytical query engine over configured local sources."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None):
        self.session = session
        self.settings = settings or get_settings()

    async def execute_sql(
        self, sql: str, selected_source_ids: list[str] | None = None
    ) -> QueryResult:
        return await asyncio.wait_for(
            asyncio.to_thread(self._execute_sql_sync, sql, selected_source_ids),
            timeout=self.settings.sql_timeout_seconds + 5,
        )

    async def materialize_for_python(
        self, work_dir: Path, selected_source_ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        return await asyncio.wait_for(
            asyncio.to_thread(self._materialize_for_python_sync, work_dir, selected_source_ids),
            timeout=self.settings.sql_timeout_seconds + 10,
        )

    def _execute_sql_sync(
        self, sql: str, selected_source_ids: list[str] | None = None
    ) -> QueryResult:
        start = time.perf_counter()
        conn = duckdb.connect(database=":memory:", read_only=False)
        try:
            tables = self._load_tables_sync(selected_source_ids)
            self._register_tables(conn, tables)
            limited_sql = (
                f"SELECT * FROM ({sql.rstrip().rstrip(';')}) AS _result "
                f"LIMIT {self.settings.sql_result_row_limit + 1}"
            )
            frame = conn.execute(limited_sql).df()
            truncated = len(frame) > self.settings.sql_result_row_limit
            if truncated:
                frame = frame.head(self.settings.sql_result_row_limit)
            rows = json_safe(frame.to_dict(orient="records"))
            return QueryResult(
                columns=[str(column) for column in frame.columns],
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
                duration_ms=(time.perf_counter() - start) * 1000,
                metadata={
                    "registered_tables": [table.canonical_name for table, _ in tables],
                    "registered_aliases": unique_table_aliases(tables),
                },
            )
        finally:
            conn.close()

    def _materialize_for_python_sync(
        self, work_dir: Path, selected_source_ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        work_dir.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(database=":memory:", read_only=False)
        try:
            tables = self._load_tables_sync(selected_source_ids)
            self._register_tables(conn, tables)
            exported: list[dict[str, Any]] = []
            for table, _source in tables:
                output = work_dir / f"{safe_filename(table.canonical_name)}.parquet"
                conn.execute(
                    f'COPY (SELECT * FROM "{table.canonical_name}") TO ? (FORMAT PARQUET)',
                    [str(output)],
                )
                exported.append(
                    {
                        "name": table.canonical_name,
                        "path": str(output),
                        "columns": [column.normalized_name for column in table.columns],
                    }
                )
            return exported
        finally:
            conn.close()

    def _load_tables_sync(
        self, selected_source_ids: list[str] | None = None
    ) -> list[tuple[TableMetadata, DataSource]]:
        """Load metadata using a short-lived synchronous SQLAlchemy-free connection.

        This method runs in a worker thread; using sqlite3 directly avoids crossing the
        async session across thread boundaries.
        """

        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from sqlalchemy.orm import selectinload as sync_selectinload

        db_url = f"sqlite:///{self.settings.metadata_db_path}"
        engine = create_engine(db_url, future=True)
        try:
            with Session(engine) as session:
                query = (
                    select(TableMetadata)
                    .options(
                        sync_selectinload(TableMetadata.columns),
                        sync_selectinload(TableMetadata.data_source),
                    )
                    .join(DataSource)
                    .where(DataSource.status == "active")
                    .order_by(TableMetadata.canonical_name)
                )
                if selected_source_ids:
                    query = query.where(TableMetadata.data_source_id.in_(selected_source_ids))
                tables = list(session.execute(query).scalars().unique().all())
                return [(table, table.data_source) for table in tables]
        finally:
            engine.dispose()

    def _register_tables(
        self, conn: duckdb.DuckDBPyConnection, tables: list[tuple[TableMetadata, DataSource]]
    ) -> None:
        sqlite_attached: set[str] = set()
        alias_map = unique_table_aliases(tables)
        for table, source in tables:
            if source.source_type == "csv":
                frame = read_csv_file(Path(source.path))
                conn.register(f"df_{table.canonical_name}", frame)
                conn.execute(
                    f'CREATE OR REPLACE VIEW "{table.canonical_name}" AS '
                    f'SELECT * FROM "df_{table.canonical_name}"'
                )
                self._register_alias_views(conn, table, alias_map)
                continue

            if source.source_type == "excel":
                frame = read_excel_sheet(Path(source.path), table.original_name, self.settings)
                conn.register(f"df_{table.canonical_name}", frame)
                conn.execute(
                    f'CREATE OR REPLACE VIEW "{table.canonical_name}" AS '
                    f'SELECT * FROM "df_{table.canonical_name}"'
                )
                self._register_alias_views(conn, table, alias_map)
                continue

            alias = f"sqlite_{source.id.replace('-', '')[:10]}"
            if self._try_attach_sqlite(conn, source, alias, sqlite_attached):
                select_list = ", ".join(
                    f'"{column.original_name}" AS "{column.normalized_name}"'
                    for column in table.columns
                )
                conn.execute(
                    f'CREATE OR REPLACE VIEW "{table.canonical_name}" AS '
                    f'SELECT {select_list} FROM "{alias}"."{table.original_name}"'
                )
            else:
                frame = self._load_sqlite_table_frame(source, table)
                conn.register(f"df_{table.canonical_name}", frame)
                conn.execute(
                    f'CREATE OR REPLACE VIEW "{table.canonical_name}" AS '
                    f'SELECT * FROM "df_{table.canonical_name}"'
                )
            self._register_alias_views(conn, table, alias_map)

    @staticmethod
    def _register_alias_views(
        conn: duckdb.DuckDBPyConnection,
        table: TableMetadata,
        alias_map: dict[str, list[str]],
    ) -> None:
        for alias in alias_map.get(table.canonical_name, []):
            conn.execute(
                f'CREATE OR REPLACE VIEW "{alias}" AS '
                f'SELECT * FROM "{table.canonical_name}"'
            )

    @staticmethod
    def _try_attach_sqlite(
        conn: duckdb.DuckDBPyConnection,
        source: DataSource,
        alias: str,
        attached: set[str],
    ) -> bool:
        if alias in attached:
            return True
        try:
            escaped_path = source.path.replace("'", "''")
            conn.execute("LOAD sqlite")
            conn.execute(f"ATTACH '{escaped_path}' AS {alias} (TYPE SQLITE, READ_ONLY)")
            attached.add(alias)
            return True
        except Exception as exc:
            logger.info("DuckDB SQLite attach unavailable, using pandas fallback: %s", exc)
            return False

    @staticmethod
    def _load_sqlite_table_frame(source: DataSource, table: TableMetadata) -> pd.DataFrame:
        uri = f"file:{source.path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            select_list = ", ".join(
                f"{quote_sqlite_identifier(column.original_name)} AS "
                f"{quote_sqlite_identifier(column.normalized_name)}"
                for column in table.columns
            )
            sql = f"SELECT {select_list} FROM {quote_sqlite_identifier(table.original_name)}"
            return pd.read_sql_query(sql, conn).convert_dtypes()
        finally:
            conn.close()
