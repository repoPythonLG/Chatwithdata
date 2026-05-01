from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from app.datasources.normalize import normalize_identifier

if TYPE_CHECKING:
    from app.db.models import DataSource, TableMetadata


def table_alias_candidates(table: TableMetadata, source: DataSource) -> list[str]:
    """Return user-friendly query aliases that are safe only when globally unique."""

    source_name = normalize_identifier(source.name, fallback="source")
    table_name = normalize_identifier(table.original_name, fallback="table")
    candidates = [source_name, table_name]
    if source_name != table_name:
        candidates.append(f"{source_name}__{table_name}")

    seen: set[str] = set()
    aliases: list[str] = []
    for alias in candidates:
        if alias and alias != table.canonical_name and alias not in seen:
            aliases.append(alias)
            seen.add(alias)
    return aliases


def unique_table_aliases(
    tables: list[tuple[TableMetadata, DataSource]],
) -> dict[str, list[str]]:
    """Map canonical table names to non-conflicting friendly aliases."""

    canonical_names = {table.canonical_name for table, _source in tables}
    candidates_by_table = {
        table.canonical_name: table_alias_candidates(table, source) for table, source in tables
    }
    counts = Counter(alias for aliases in candidates_by_table.values() for alias in aliases)
    return {
        canonical_name: [
            alias
            for alias in aliases
            if counts[alias] == 1 and alias not in canonical_names
        ]
        for canonical_name, aliases in candidates_by_table.items()
    }
