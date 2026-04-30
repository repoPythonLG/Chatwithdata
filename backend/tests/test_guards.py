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


def test_python_guard_blocks_unsafe_imports_and_calls():
    guard = PythonGuard(max_chars=2000)
    result = guard.validate("import os\nos.system('rm -rf /')\n")

    assert not result.is_valid
    assert any("Import is not allowed" in error for error in result.errors)
