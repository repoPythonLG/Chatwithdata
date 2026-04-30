from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.agent.python_sandbox import PythonSandbox
from app.datasources.catalog import DataSourceCatalog
from app.datasources.query_engine import QueryEngine


class SqlToolInput(BaseModel):
    sql: str
    selected_data_sources: list[str] | None = None


class PythonToolInput(BaseModel):
    code: str
    selected_data_sources: list[str] | None = None


def build_langchain_tools(
    catalog: DataSourceCatalog,
    query_engine: QueryEngine,
    python_sandbox: PythonSandbox,
) -> list[StructuredTool]:
    """Expose core capabilities as LangChain tools for future tool-calling agents.

    The LangGraph workflow calls services directly for deterministic control, while
    these tools make the same capabilities available to LangChain-based extensions.
    """

    async def inspect_schema(selected_data_sources: list[str] | None = None) -> str:
        return await catalog.compact_schema_text(selected_data_sources)

    async def execute_sql(
        sql: str, selected_data_sources: list[str] | None = None
    ) -> dict[str, Any]:
        result = await query_engine.execute_sql(sql, selected_data_sources)
        return {
            "columns": result.columns,
            "rows": result.rows,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "duration_ms": result.duration_ms,
        }

    async def execute_python(
        code: str, selected_data_sources: list[str] | None = None
    ) -> dict[str, Any]:
        result = await python_sandbox.execute(code, selected_data_sources)
        return {
            "ok": result.ok,
            "answer": result.answer,
            "stdout": result.stdout,
            "result_table": result.result_table,
            "chart": result.chart,
            "error": result.error,
        }

    return [
        StructuredTool.from_function(
            coroutine=inspect_schema,
            name="inspect_schema",
            description="Inspect the current normalized metadata catalog.",
        ),
        StructuredTool.from_function(
            coroutine=execute_sql,
            name="execute_readonly_sql",
            description="Execute validated read-only SQL over approved data sources.",
            args_schema=SqlToolInput,
        ),
        StructuredTool.from_function(
            coroutine=execute_python,
            name="execute_sandboxed_python",
            description="Run validated sandboxed Python analysis over approved data sources.",
            args_schema=PythonToolInput,
        ),
    ]
