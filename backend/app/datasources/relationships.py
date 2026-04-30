from __future__ import annotations

from app.db.models import TableMetadata


def infer_relationships(tables: list[TableMetadata]) -> list[dict[str, object]]:
    """Infer likely joins from primary keys and common naming conventions."""

    inferred: list[dict[str, object]] = []
    table_by_base: dict[str, TableMetadata] = {}
    primary_keys: dict[str, set[str]] = {}

    for table in tables:
        base = table.canonical_name.split("__")[-1]
        table_by_base[base] = table
        primary_keys[table.canonical_name] = {
            column.normalized_name
            for column in table.columns
            if column.profile.get("primary_key_position")
            or column.normalized_name in {"id", f"{base}_id"}
        }

    seen: set[tuple[str, str, str, str]] = set()
    for left in tables:
        for column in left.columns:
            name = column.normalized_name
            if not name.endswith("_id"):
                continue
            prefix = name.removesuffix("_id")
            candidates = {prefix, f"{prefix}s", f"{prefix}es"}
            for candidate in candidates:
                right = table_by_base.get(candidate)
                if not right or right.canonical_name == left.canonical_name:
                    continue
                right_keys = primary_keys.get(right.canonical_name) or {"id", name}
                right_col = "id" if "id" in right_keys else sorted(right_keys)[0]
                key = (left.canonical_name, name, right.canonical_name, right_col)
                if key in seen:
                    continue
                seen.add(key)
                inferred.append(
                    {
                        "left_table": left.canonical_name,
                        "left_column": name,
                        "right_table": right.canonical_name,
                        "right_column": right_col,
                        "confidence": 0.72,
                        "evidence": "Column naming convention suggests a foreign-key relationship",
                    }
                )

    return inferred
