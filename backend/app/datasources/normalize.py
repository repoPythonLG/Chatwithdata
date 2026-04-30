from __future__ import annotations

import re
from pathlib import Path


def normalize_identifier(value: object, *, fallback: str = "column") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[\s\-/\\.:;,#()\[\]{}]+", "_", text)
    text = re.sub(r"[^a-z0-9_]", "", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = fallback
    if text[0].isdigit():
        text = f"{fallback}_{text}"
    return text


def dedupe_identifiers(values: list[object], *, fallback: str = "column") -> list[str]:
    counts: dict[str, int] = {}
    result: list[str] = []
    for value in values:
        base = normalize_identifier(value, fallback=fallback)
        counts[base] = counts.get(base, 0) + 1
        result.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return result


def canonical_source_prefix(source_name: str, source_id: str) -> str:
    stem = normalize_identifier(
        Path(source_name).stem if source_name else source_id, fallback="source"
    )
    short_id = source_id.replace("-", "")[:8]
    return f"{stem}_{short_id}"


def canonical_table_name(source_name: str, source_id: str, table_name: str) -> str:
    table = normalize_identifier(table_name, fallback="table")
    return f"{canonical_source_prefix(source_name, source_id)}__{table}"
