from app.agent.python_guard import PythonGuard
from app.agent.sql_guard import SqlGuard


def test_sql_guard_accepts_known_readonly_query():
    guard = SqlGuard()
    result = guard.validate(
        "SELECT customer_name FROM sales__customers WHERE region = 'North' LIMIT 5",
        {"sales__customers": {"customer_name", "region"}},
    )

    assert result.is_valid
    assert result.used_tables == ["sales__customers"]


def test_sql_guard_rejects_mutation():
    guard = SqlGuard()
    result = guard.validate("DROP TABLE sales__customers", {"sales__customers": {"id"}})

    assert not result.is_valid
    assert result.errors


def test_sql_guard_accepts_cte_aliases_for_readonly_queries():
    guard = SqlGuard()
    result = guard.validate(
        """
        WITH means AS (
            SELECT 'revenue' AS column_name, AVG("revenue") AS mean_value
            FROM "sales__orders"
        )
        SELECT column_name, mean_value FROM means
        """,
        {"sales__orders": {"revenue"}},
    )

    assert result.is_valid
    assert result.used_tables == ["sales__orders"]


def test_python_guard_blocks_unsafe_imports_and_calls():
    guard = PythonGuard(max_chars=2000)
    result = guard.validate("import os\nos.system('rm -rf /')\n")

    assert not result.is_valid
    assert any("Import is not allowed" in error for error in result.errors)


def test_python_guard_rejects_raw_sql_text():
    guard = PythonGuard(max_chars=2000)
    result = guard.validate("SELECT * FROM sales__orders")

    assert not result.is_valid
    assert any("returned raw SQL" in error for error in result.errors)


def test_python_guard_allows_chart_json_and_pandas_transformations():
    guard = PythonGuard(max_chars=2000)
    result = guard.validate(
        """
import json

df = sql_result_df.rename(columns={"old": "new"}).replace({"n/a": None})
chart = {
    "data": [{"type": "bar", "x": df["new"].tolist(), "y": df["value"].tolist()}],
    "layout": {"title": json.dumps({"text": "Example"})}
}
answer = "Created a chart."
"""
    )

    assert result.is_valid
    assert not result.errors
    assert not result.warnings
