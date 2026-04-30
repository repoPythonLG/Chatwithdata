from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import Settings
from app.datasources.normalize import canonical_table_name, dedupe_identifiers
from app.datasources.profiling import dataframe_sample_rows, file_checksum, json_safe

logger = logging.getLogger(__name__)


EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xls"}


def detect_header_row(raw: pd.DataFrame) -> int:
    """Choose the row that looks most like headers among the first rows."""

    best_index = 0
    best_score = -1
    for index, row in raw.iterrows():
        values = [str(value).strip() for value in row.tolist() if not pd.isna(value)]
        if not values:
            continue
        unique = len(set(values))
        alpha = sum(any(ch.isalpha() for ch in value) for value in values)
        score = unique + alpha - abs(index) * 0.05
        if score > best_score:
            best_score = score
            best_index = int(index)
    return best_index


def read_excel_sheet(path: Path, sheet_name: str, settings: Settings) -> pd.DataFrame:
    preview = pd.read_excel(path, sheet_name=sheet_name, header=None, nrows=30)
    header_row = detect_header_row(preview)
    df = pd.read_excel(path, sheet_name=sheet_name, header=header_row)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    normalized = dedupe_identifiers(list(df.columns), fallback="column")
    df.columns = normalized
    return df.convert_dtypes()


class ExcelScanner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def scan(self, source_id: str, source_name: str, path: Path) -> dict[str, Any]:
        if path.suffix.lower() not in EXCEL_EXTENSIONS:
            raise ValueError(f"Unsupported Excel extension: {path.suffix}")

        workbook = pd.ExcelFile(path)
        tables: list[dict[str, Any]] = []
        for sheet_name in workbook.sheet_names:
            try:
                df = read_excel_sheet(path, sheet_name, self.settings)
            except Exception as exc:
                logger.warning("Skipping unreadable sheet %s in %s: %s", sheet_name, path, exc)
                continue

            if df.empty and not len(df.columns):
                continue

            columns: list[dict[str, Any]] = []
            for index, column in enumerate(df.columns):
                series = df[column]
                non_null = series.dropna()
                columns.append(
                    {
                        "original_name": str(column),
                        "normalized_name": str(column),
                        "data_type": str(series.dtype),
                        "nullable": bool(series.isna().any()),
                        "null_count": int(series.isna().sum()),
                        "sample_values": json_safe(
                            non_null.astype("object")
                            .head(self.settings.metadata_profile_value_limit)
                            .tolist()
                        ),
                        "ordinal": index,
                        "profile": {
                            "distinct_sample_count": int(non_null.astype(str).nunique(dropna=True))
                        },
                    }
                )

            tables.append(
                {
                    "database_name": path.name,
                    "original_name": sheet_name,
                    "canonical_name": canonical_table_name(source_name, source_id, sheet_name),
                    "kind": "sheet",
                    "row_count": int(len(df)),
                    "sample_rows": dataframe_sample_rows(df, self.settings.metadata_sample_rows),
                    "profile": {"source_file": str(path), "sheet_name": sheet_name},
                    "columns": columns,
                }
            )

        return {
            "checksum": file_checksum(path),
            "profile": {"sheet_count": len(workbook.sheet_names), "extension": path.suffix.lower()},
            "tables": tables,
            "relationships": [],
        }
