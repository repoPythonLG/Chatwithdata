from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import Settings
from app.datasources.normalize import canonical_table_name, dedupe_identifiers
from app.datasources.profiling import dataframe_sample_rows, file_checksum, json_safe

CSV_EXTENSIONS = {".csv", ".tsv"}


def read_csv_file(path: Path) -> pd.DataFrame:
    separator = "\t" if path.suffix.lower() == ".tsv" else None
    read_kwargs = {
        "sep": separator,
        "engine": "python" if separator is None else None,
        "encoding": "utf-8-sig",
    }
    read_kwargs = {key: value for key, value in read_kwargs.items() if value is not None}

    try:
        df = pd.read_csv(path, **read_kwargs)
    except UnicodeDecodeError:
        read_kwargs["encoding"] = "latin1"
        df = pd.read_csv(path, **read_kwargs)

    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    df.columns = dedupe_identifiers(list(df.columns), fallback="column")
    return df.convert_dtypes()


class CSVScanner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def scan(self, source_id: str, source_name: str, path: Path) -> dict[str, Any]:
        if path.suffix.lower() not in CSV_EXTENSIONS:
            raise ValueError(f"Unsupported CSV extension: {path.suffix}")

        df = read_csv_file(path)
        table_name = path.stem
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

        return {
            "checksum": file_checksum(path),
            "profile": {
                "extension": path.suffix.lower(),
                "delimiter": "tab" if path.suffix.lower() == ".tsv" else "auto",
            },
            "tables": [
                {
                    "database_name": path.name,
                    "original_name": table_name,
                    "canonical_name": canonical_table_name(source_name, source_id, table_name),
                    "kind": "csv",
                    "row_count": int(len(df)),
                    "sample_rows": dataframe_sample_rows(df, self.settings.metadata_sample_rows),
                    "profile": {"source_file": str(path)},
                    "columns": columns,
                }
            ],
            "relationships": [],
        }
