from __future__ import annotations

import contextlib
import importlib
import io
import json
import math
import statistics
import sys
from datetime import date, datetime
from typing import Any

import duckdb
import numpy as np
import pandas as pd

ALLOWED_IMPORT_ROOTS = {"datetime", "duckdb", "math", "numpy", "pandas", "plotly", "statistics"}


def json_safe(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value) and not isinstance(value, (list, tuple, dict)):
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
    if isinstance(value, pd.DataFrame):
        return [json_safe(row) for row in value.head(200).to_dict(orient="records")]
    if isinstance(value, pd.Series):
        return json_safe(value.head(200).tolist())
    if isinstance(value, dict):
        return {str(key): json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def safe_import(
    name: str, globals_: dict | None = None, locals_: dict | None = None, fromlist=(), level=0
):
    root = name.split(".")[0]
    if root not in ALLOWED_IMPORT_ROOTS:
        raise ImportError(f"Import is not allowed in sandbox: {name}")
    return importlib.import_module(name)


def build_builtins() -> dict[str, Any]:
    allowed_names = [
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "filter",
        "float",
        "int",
        "len",
        "list",
        "map",
        "max",
        "min",
        "pow",
        "print",
        "range",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
    ]
    builtins_module = importlib.import_module("builtins")
    builtins = {name: getattr(builtins_module, name) for name in allowed_names}
    builtins["__import__"] = safe_import
    return builtins


def main() -> None:
    payload = json.loads(sys.stdin.read())
    tables = payload["tables"]
    code = payload["code"]

    conn = duckdb.connect(database=":memory:", read_only=False)
    try:
        for table in tables:
            path = table["path"].replace("'", "''")
            name = table["name"].replace('"', '""')
            conn.execute(
                f"CREATE OR REPLACE VIEW \"{name}\" AS SELECT * FROM read_parquet('{path}')"
            )

        def query(sql: str) -> pd.DataFrame:
            blocked = (
                "attach",
                "copy",
                "create",
                "delete",
                "drop",
                "insert",
                "install",
                "load",
                "pragma",
                "update",
            )
            lowered = sql.lower()
            if any(f"{word} " in lowered or lowered.strip().startswith(word) for word in blocked):
                raise ValueError("Only read-only SELECT queries are available through query(sql).")
            return conn.execute(sql).df()

        stdout = io.StringIO()
        globals_dict: dict[str, Any] = {
            "__builtins__": build_builtins(),
            "pd": pd,
            "np": np,
            "duckdb": duckdb,
            "math": math,
            "statistics": statistics,
            "query": query,
            "tables": [
                {key: value for key, value in table.items() if key != "path"} for table in tables
            ],
        }
        locals_dict: dict[str, Any] = {}
        with contextlib.redirect_stdout(stdout):
            exec(compile(code, "<sandbox>", "exec"), globals_dict, locals_dict)

        answer = locals_dict.get("answer") or globals_dict.get("answer")
        result_table = (
            locals_dict.get("result_table")
            or globals_dict.get("result_table")
            or locals_dict.get("result")
            or globals_dict.get("result")
        )
        chart = locals_dict.get("chart") or globals_dict.get("chart")

        chart_spec = None
        if chart is not None:
            if hasattr(chart, "to_plotly_json"):
                chart_spec = chart.to_plotly_json()
            elif isinstance(chart, dict):
                chart_spec = chart

        output = {
            "ok": True,
            "answer": str(answer) if answer is not None else "",
            "stdout": stdout.getvalue(),
            "result_table": json_safe(result_table) if result_table is not None else [],
            "chart": json_safe(chart_spec) if chart_spec is not None else None,
        }
        print(json.dumps(output))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
