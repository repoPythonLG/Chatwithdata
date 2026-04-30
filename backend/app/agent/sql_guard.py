from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp


@dataclass
class SqlValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    used_tables: list[str] = field(default_factory=list)
    used_columns: dict[str, list[str]] = field(default_factory=dict)


class SqlGuard:
    """Static SQL validator for read-only DuckDB queries over known tables."""

    dangerous_keyword_pattern = re.compile(
        r"\b("
        r"insert|update|delete|merge|drop|alter|create|replace|truncate|vacuum|attach|detach|"
        r"copy|load|install|pragma|grant|revoke|call|execute|prepare|export|import"
        r")\b",
        re.IGNORECASE,
    )
    blocked_functions = {
        "read_csv",
        "read_json",
        "read_parquet",
        "read_text",
        "read_blob",
        "httpfs",
        "url_encode",
        "writefile",
        "readfile",
    }

    def validate(self, sql: str, table_columns: dict[str, set[str]]) -> SqlValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        stripped = sql.strip()
        if not stripped:
            return SqlValidationResult(False, ["SQL query is empty"])

        if self.dangerous_keyword_pattern.search(stripped):
            errors.append("Only read-only SELECT/WITH queries are allowed.")
        if self._has_outer_grouped_union_aggregation(stripped):
            warnings.append(
                "Check whether each UNION branch is aggregated at the right grain before "
                "combining grouped counts."
            )

        try:
            parsed = sqlglot.parse(stripped, read="duckdb")
        except Exception as exc:
            return SqlValidationResult(False, [f"SQL parse error: {exc}"])

        if len(parsed) != 1:
            errors.append("Multiple SQL statements are not allowed.")

        tree = parsed[0]
        if not (isinstance(tree, (exp.Select, exp.Union)) or tree.find(exp.Select)):
            errors.append("SQL must be a SELECT, WITH, or UNION query.")

        for func in tree.find_all(exp.Func):
            if func.sql_name().lower() in self.blocked_functions:
                errors.append(f"Function {func.sql_name()} is not allowed.")

        cte_names = {cte.alias for cte in tree.find_all(exp.CTE) if cte.alias}
        referenced_tables: list[str] = []
        aliases: dict[str, str] = {}
        for table in tree.find_all(exp.Table):
            table_name = table.name
            if table_name in cte_names:
                aliases[table.alias_or_name] = table_name
                continue
            referenced_tables.append(table_name)
            alias = table.alias_or_name
            aliases[alias] = table_name
            if table_name not in table_columns:
                errors.append(f"Unknown table: {table_name}")

        projection_aliases = {
            projection.alias
            for projection in tree.expressions
            if isinstance(projection, exp.Alias) and projection.alias
        }
        used_columns: dict[str, set[str]] = {table: set() for table in referenced_tables}
        available_columns = {
            column for table in referenced_tables for column in table_columns.get(table, set())
        }

        has_derived_tables = bool(list(tree.find_all(exp.Subquery)))

        for column in tree.find_all(exp.Column):
            column_name = column.name
            if column_name == "*":
                warnings.append("SELECT * should only be used for tiny previews.")
                continue
            qualifier = column.table
            if qualifier:
                table_name = aliases.get(qualifier, qualifier)
                if table_name in cte_names:
                    continue
                if table_name in table_columns and column_name not in table_columns[table_name]:
                    errors.append(f"Unknown column: {qualifier}.{column_name}")
                used_columns.setdefault(table_name, set()).add(column_name)
            elif (
                referenced_tables
                and column_name not in available_columns
                and column_name not in projection_aliases
                and not cte_names
                and not has_derived_tables
            ):
                errors.append(f"Unknown unqualified column: {column_name}")

        errors.extend(self._order_by_projection_errors(tree, available_columns))

        return SqlValidationResult(
            is_valid=not errors,
            errors=errors,
            warnings=warnings,
            used_tables=sorted(set(referenced_tables)),
            used_columns={key: sorted(value) for key, value in used_columns.items() if value},
        )

    @staticmethod
    def _order_by_projection_errors(
        tree: exp.Expression, available_columns: set[str]
    ) -> list[str]:
        errors: list[str] = []
        for select in tree.find_all(exp.Select):
            order = select.args.get("order")
            if not order:
                continue
            projected_names: set[str] = set()
            has_star = False
            for projection in select.expressions:
                if isinstance(projection, exp.Star):
                    has_star = True
                    continue
                alias = projection.alias
                if alias:
                    projected_names.add(alias.lower())
                expression = projection.this if isinstance(projection, exp.Alias) else projection
                if isinstance(expression, exp.Column):
                    projected_names.add(expression.name.lower())
            if has_star:
                continue

            for ordered in order.expressions:
                for column in ordered.find_all(exp.Column):
                    column_name = column.name
                    if (
                        column_name
                        and column_name in available_columns
                        and column_name.lower() not in projected_names
                    ):
                        errors.append(
                            "ORDER BY column must appear in the SELECT output for "
                            f"auditable results: {column_name}"
                        )
        return errors

    @staticmethod
    def _has_outer_grouped_union_aggregation(sql: str) -> bool:
        normalized = re.sub(r"\s+", " ", sql.strip().lower())
        return bool(
            re.search(
                r"from\s*\(\s*select\b.+\bunion\s+all\b.+\)\s+as\s+\"?[\w_]+\"?\s+group\s+by",
                normalized,
            )
            and "count(" in normalized
        )
