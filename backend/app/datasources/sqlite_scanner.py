from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.datasources.normalize import canonical_table_name, dedupe_identifiers
from app.datasources.profiling import file_checksum, json_safe


def quote_sqlite_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


class SQLiteScanner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def scan(self, source_id: str, source_name: str, path: Path) -> dict[str, Any]:
        checksum = file_checksum(path)
        uri = f"file:{path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            tables = self._scan_tables(conn, source_id, source_name, path)
            relationships = self._scan_declared_relationships(conn, tables)
            return {
                "checksum": checksum,
                "profile": {"sqlite_version": sqlite3.sqlite_version},
                "tables": tables,
                "relationships": relationships,
            }
        finally:
            conn.close()

    def _scan_tables(
        self, conn: sqlite3.Connection, source_id: str, source_name: str, path: Path
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT name, type
            FROM sqlite_master
            WHERE type IN ('table', 'view')
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

        tables: list[dict[str, Any]] = []
        for row in rows:
            original_name = row["name"]
            kind = row["type"]
            canonical = canonical_table_name(source_name, source_id, original_name)
            pragma_rows = conn.execute(
                f"PRAGMA table_info({quote_sqlite_identifier(original_name)})"
            ).fetchall()
            normalized_columns = dedupe_identifiers([col["name"] for col in pragma_rows])
            original_to_normalized = {
                col["name"]: normalized_columns[index] for index, col in enumerate(pragma_rows)
            }

            row_count = self._safe_scalar(
                conn, f"SELECT COUNT(*) FROM {quote_sqlite_identifier(original_name)}"
            )
            sample_rows = self._sample_rows(conn, original_name, original_to_normalized)

            columns = []
            for index, col in enumerate(pragma_rows):
                original_column = col["name"]
                normalized = normalized_columns[index]
                null_count = self._safe_scalar(
                    conn,
                    f"SELECT COUNT(*) FROM {quote_sqlite_identifier(original_name)} "
                    f"WHERE {quote_sqlite_identifier(original_column)} IS NULL",
                )
                sample_values = conn.execute(
                    f"SELECT DISTINCT {quote_sqlite_identifier(original_column)} AS value "
                    f"FROM {quote_sqlite_identifier(original_name)} "
                    f"WHERE {quote_sqlite_identifier(original_column)} IS NOT NULL "
                    f"LIMIT {self.settings.metadata_profile_value_limit}"
                ).fetchall()
                columns.append(
                    {
                        "original_name": original_column,
                        "normalized_name": normalized,
                        "data_type": col["type"] or "UNKNOWN",
                        "nullable": not bool(col["notnull"]),
                        "null_count": null_count,
                        "sample_values": json_safe([value["value"] for value in sample_values]),
                        "ordinal": index,
                        "profile": {"primary_key_position": col["pk"] or None},
                    }
                )

            tables.append(
                {
                    "database_name": path.name,
                    "original_name": original_name,
                    "canonical_name": canonical,
                    "kind": kind,
                    "row_count": row_count,
                    "sample_rows": sample_rows,
                    "profile": {
                        "source_file": str(path),
                        "original_to_normalized": original_to_normalized,
                    },
                    "columns": columns,
                }
            )
        return tables

    def _sample_rows(
        self, conn: sqlite3.Connection, table: str, original_to_normalized: dict[str, str]
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            f"SELECT * FROM {quote_sqlite_identifier(table)} "
            f"LIMIT {self.settings.metadata_sample_rows}"
        ).fetchall()
        samples = []
        for row in rows:
            keys = row.keys()
            samples.append(
                {original_to_normalized.get(key, key): json_safe(row[key]) for key in keys}
            )
        return samples

    @staticmethod
    def _safe_scalar(conn: sqlite3.Connection, sql: str) -> int | None:
        try:
            return int(conn.execute(sql).fetchone()[0])
        except Exception:
            return None

    def _scan_declared_relationships(
        self, conn: sqlite3.Connection, tables: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        by_original = {table["original_name"]: table for table in tables}
        relationships: list[dict[str, Any]] = []
        for table in tables:
            original_name = table["original_name"]
            fk_rows = conn.execute(
                f"PRAGMA foreign_key_list({quote_sqlite_identifier(original_name)})"
            ).fetchall()
            for fk in fk_rows:
                target = by_original.get(fk["table"])
                if not target:
                    continue
                left_col = table["profile"]["original_to_normalized"].get(fk["from"], fk["from"])
                right_col = target["profile"]["original_to_normalized"].get(fk["to"], fk["to"])
                relationships.append(
                    {
                        "left_table": table["canonical_name"],
                        "left_column": left_col,
                        "right_table": target["canonical_name"],
                        "right_column": right_col,
                        "confidence": 1.0,
                        "evidence": "Declared SQLite foreign key",
                    }
                )
        return relationships
