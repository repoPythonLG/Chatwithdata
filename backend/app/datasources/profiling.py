from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_safe(value: Any) -> Any:
    if value is None:
        return None
    try:
        if not isinstance(value, (list, tuple, dict)) and pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def dataframe_sample_rows(df: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
    if df.empty:
        return []
    records = df.head(limit).to_dict(orient="records")
    return [json_safe(record) for record in records]


def dataframe_columns(df: pd.DataFrame, sample_value_limit: int) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    for index, name in enumerate(df.columns):
        series = df[name]
        non_null = series.dropna()
        sample_values = non_null.astype("object").head(sample_value_limit).tolist()
        columns.append(
            {
                "original_name": str(name),
                "normalized_name": str(name),
                "data_type": str(series.dtype),
                "nullable": bool(series.isna().any()),
                "null_count": int(series.isna().sum()),
                "sample_values": json_safe(sample_values),
                "ordinal": index,
                "profile": {
                    "distinct_sample_count": int(non_null.astype(str).nunique(dropna=True)),
                },
            }
        )
    return columns
