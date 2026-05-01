from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import (
    AMBIGUITY_RESOLVER_SYSTEM,
    CLASSIFIER_SYSTEM,
    CRITIC_SYSTEM,
    FINAL_SYSTEM,
    METADATA_OVERVIEW_CRITIC_SYSTEM,
    METADATA_OVERVIEW_SYSTEM,
    PLAN_AUDIT_SYSTEM,
    PLANNER_SYSTEM,
    PYTHON_SYSTEM,
    QUESTION_SUGGESTIONS_CRITIC_SYSTEM,
    QUESTION_SUGGESTIONS_SYSTEM,
    SQL_CRITIC_SYSTEM,
    SQL_QUALITY_AUDIT_SYSTEM,
    SQL_SYSTEM,
)
from app.agent.python_guard import PythonGuard
from app.agent.python_sandbox import PythonSandbox
from app.agent.sql_guard import SqlGuard
from app.agent.state import AgentState
from app.agent.text_sanitizer import sanitize_user_text
from app.core.config import get_settings
from app.core.llm import LLMClient
from app.datasources.catalog import DataSourceCatalog
from app.datasources.query_engine import QueryEngine

MAX_SQL_ATTEMPTS = 3
MAX_PYTHON_ATTEMPTS = 3
MAX_CRITIQUE_ATTEMPTS = 3


def status_event(step: str, status: str, message: str, **metadata: Any) -> dict[str, Any]:
    return {
        "step": step,
        "status": status,
        "message": sanitize_user_text(message),
        "timestamp": datetime.utcnow().isoformat(),
        "metadata": metadata,
    }


def add_event(state: AgentState, step: str, status: str, message: str, **metadata: Any) -> None:
    state.setdefault("status_events", []).append(status_event(step, status, message, **metadata))


class DataChatAgent:
    def __init__(self, session: AsyncSession, llm: LLMClient | None = None):
        self.session = session
        self.settings = get_settings()
        self.catalog = DataSourceCatalog(session)
        self.query_engine = QueryEngine(session, self.settings)
        self.llm = llm or LLMClient(self.settings)
        self.sql_guard = SqlGuard()
        self.python_guard = PythonGuard(self.settings.python_max_code_chars)
        self.python_sandbox = PythonSandbox(self.query_engine, self.settings)
        self.graph = self._build_graph()

    async def run(self, initial_state: AgentState) -> AgentState:
        return await self.graph.ainvoke(self._with_defaults(initial_state))

    async def stream_states(self, initial_state: AgentState) -> AsyncIterator[AgentState]:
        async for state in self.graph.astream(
            self._with_defaults(initial_state), stream_mode="values"
        ):
            yield state

    def _with_defaults(self, state: AgentState) -> AgentState:
        state.setdefault("messages", [])
        state.setdefault("errors", [])
        state.setdefault("status_events", [])
        state.setdefault("artifacts", [])
        state.setdefault("sql_attempts", 0)
        state.setdefault("python_attempts", 0)
        state.setdefault("critique_attempts", 0)
        return state

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("receive_question", self.receive_question)
        graph.add_node("classify_question", self.classify_question)
        graph.add_node("inspect_schema", self.inspect_schema)
        graph.add_node("plan_answer", self.plan_answer)
        graph.add_node("generate_sql", self.generate_sql)
        graph.add_node("validate_sql", self.validate_sql)
        graph.add_node("execute_sql", self.execute_sql)
        graph.add_node("generate_python", self.generate_python)
        graph.add_node("validate_python", self.validate_python)
        graph.add_node("execute_python", self.execute_python)
        graph.add_node("critique_answer", self.critique_answer)
        graph.add_node("final_response", self.final_response)

        graph.set_entry_point("receive_question")
        graph.add_edge("receive_question", "classify_question")
        graph.add_edge("classify_question", "inspect_schema")
        graph.add_edge("inspect_schema", "plan_answer")
        graph.add_conditional_edges(
            "plan_answer",
            self.route_after_plan,
            {
                "sql": "generate_sql",
                "python": "generate_python",
                "final": "final_response",
            },
        )
        graph.add_edge("generate_sql", "validate_sql")
        graph.add_conditional_edges(
            "validate_sql",
            self.route_after_sql_validation,
            {
                "execute": "execute_sql",
                "repair": "generate_sql",
                "python": "generate_python",
                "final": "final_response",
            },
        )
        graph.add_conditional_edges(
            "execute_sql",
            self.route_after_sql_execution,
            {
                "critique": "critique_answer",
                "repair": "generate_sql",
                "python": "generate_python",
                "final": "final_response",
            },
        )
        graph.add_edge("generate_python", "validate_python")
        graph.add_conditional_edges(
            "validate_python",
            self.route_after_python_validation,
            {"execute": "execute_python", "repair": "generate_python", "final": "final_response"},
        )
        graph.add_conditional_edges(
            "execute_python",
            self.route_after_python_execution,
            {"critique": "critique_answer", "repair": "generate_python", "final": "final_response"},
        )
        graph.add_conditional_edges(
            "critique_answer",
            self.route_after_critique,
            {"sql": "generate_sql", "python": "generate_python", "final": "final_response"},
        )
        graph.add_edge("final_response", END)
        return graph.compile()

    async def receive_question(self, state: AgentState) -> AgentState:
        add_event(state, "Planning", "running", "Received the question and conversation context.")
        question = state.get("user_question", "").strip()
        if not question:
            state["errors"].append("Question is empty.")
        add_event(state, "Planning", "completed", "Input validation completed.")
        return state

    async def classify_question(self, state: AgentState) -> AgentState:
        add_event(state, "Planning", "running", "Classifying the analysis request.")
        prompt = [
            {"role": "system", "content": CLASSIFIER_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": state["user_question"],
                        "recent_messages": state.get("messages", [])[-6:],
                    }
                ),
            },
        ]
        try:
            classification = await self.llm.complete_json(prompt)
        except Exception as exc:
            classification = self._fallback_classification(state["user_question"])
            classification["llm_warning"] = str(exc)
        state["classification"] = classification
        state["question_type"] = classification.get("question_type", "sql_answerable")
        add_event(
            state,
            "Planning",
            "completed",
            f"Classified as {state['question_type']}.",
        )
        return state

    async def inspect_schema(self, state: AgentState) -> AgentState:
        add_event(state, "Inspecting schema", "running", "Retrieving current metadata catalog.")
        selected = state.get("selected_data_sources")
        state["schema_context"] = await self.catalog.compact_schema_text(selected)
        state["table_columns"] = await self.catalog.table_column_map(selected)
        if state["schema_context"] == "No data sources are configured.":
            state["classification"] = {"question_type": "impossible"}
            state["question_type"] = "impossible"
        add_event(state, "Inspecting schema", "completed", "Schema context is ready.")
        return state

    async def plan_answer(self, state: AgentState) -> AgentState:
        add_event(state, "Planning", "running", "Creating a bounded execution plan.")
        if state.get("question_type") == "impossible":
            state["execution_plan"] = {
                "tool": "none",
                "steps": ["No configured data sources are available."],
                "requires_chart": False,
                "clarification_question": None,
            }
            add_event(state, "Planning", "warning", "No usable data sources are configured.")
            return state

        if state.get("question_type") == "ambiguous":
            await self.resolve_ambiguity_with_schema(state)

        if state.get("question_type") == "question_suggestions":
            state["execution_plan"] = self._question_suggestions_plan()
            add_event(state, "Planning", "completed", "Plan selected LLM question suggestions.")
            return state

        if state.get("question_type") == "ambiguous":
            state["execution_plan"] = self._clarification_plan(state)
            add_event(
                state, "Planning", "warning", "Question needs clarification before execution."
            )
            return state

        prompt = [
            {"role": "system", "content": PLANNER_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": state["user_question"],
                        "classification": state.get("classification", {}),
                        "schema": state.get("schema_context", ""),
                        "schema_interpretation": state.get("schema_interpretation", {}),
                        "recent_messages": state.get("messages", [])[-6:],
                    }
                ),
            },
        ]
        try:
            plan = await self.llm.complete_json(prompt)
        except Exception as exc:
            plan = self._fallback_plan(state["user_question"], state.get("question_type", ""))
            plan["llm_warning"] = str(exc)
        plan = await self._audit_execution_plan(state, plan)
        if (
            plan.get("tool") == "python"
            and state.get("question_type") == "requires_chart"
        ):
            plan["tool"] = "sql"
            plan["python_deferred_reason"] = (
                "Chart-ready tabular analysis is routed through SQL first; Python remains "
                "available as a repair fallback."
            )
        state["execution_plan"] = plan
        add_event(
            state, "Planning", "completed", f"Plan selected {plan.get('tool', 'sql')} execution."
        )
        return state

    async def _audit_execution_plan(
        self, state: AgentState, plan: dict[str, Any]
    ) -> dict[str, Any]:
        prompt = [
            {"role": "system", "content": PLAN_AUDIT_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": state["user_question"],
                        "classification": state.get("classification", {}),
                        "proposed_plan": plan,
                        "schema": state.get("schema_context", ""),
                        "recent_messages": state.get("messages", [])[-8:],
                    }
                ),
            },
        ]
        try:
            audit = await self.llm.complete_json(prompt, max_tokens=900)
        except Exception as exc:
            plan["plan_audit_warning"] = str(exc)
            return plan

        if not isinstance(audit, dict):
            return plan
        audited_tool = str(audit.get("tool") or "").strip()
        if audited_tool in {"question_suggestions", "metadata", "sql", "python", "clarify", "none"}:
            if not self._json_bool(audit.get("passes"), default=True):
                plan = {**plan, "tool": audited_tool}
                plan["plan_audit_reasoning_summary"] = audit.get("reasoning_summary", "")
        return plan

    async def generate_sql(self, state: AgentState) -> AgentState:
        repair_feedback = self._sql_repair_feedback(state)
        state["sql_attempts"] = int(state.get("sql_attempts", 0)) + 1
        add_event(
            state,
            "Generating query",
            "running",
            f"Generating SQL attempt {state['sql_attempts']}.",
        )
        state.pop("sql_validation", None)
        state.pop("sql_result", None)
        prompt = [
            {"role": "system", "content": SQL_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": state["user_question"],
                        "schema": state.get("schema_context", ""),
                        "schema_interpretation": state.get("schema_interpretation", {}),
                        "plan": state.get("execution_plan", {}),
                        "recent_messages": state.get("messages", [])[-8:],
                        "attempt": state["sql_attempts"],
                        "repair_feedback": repair_feedback,
                        "previous_errors": state.get("errors", [])[-5:],
                    }
                ),
            },
        ]
        try:
            payload = await self.llm.complete_json(prompt)
            state["sql_query"] = (payload.get("sql") or "").strip()
            if payload.get("reasoning_summary"):
                state["execution_plan"]["sql_reasoning_summary"] = payload["reasoning_summary"]
        except Exception as exc:
            state["sql_query"] = ""
            state["errors"].append(f"SQL generation failed: {exc}")
        add_event(state, "Generating query", "completed", "SQL generation finished.")
        return state

    async def validate_sql(self, state: AgentState) -> AgentState:
        add_event(state, "Validating", "running", "Validating generated SQL against safety policy.")
        result = self.sql_guard.validate(state.get("sql_query", ""), state.get("table_columns", {}))
        state["sql_validation"] = {
            "is_valid": result.is_valid,
            "errors": result.errors,
            "warnings": result.warnings,
            "used_tables": result.used_tables,
            "used_columns": result.used_columns,
        }
        if not result.is_valid:
            state["errors"].extend(result.errors)
            add_event(state, "Validating", "error", "SQL validation failed.", errors=result.errors)
            return state

        critique = await self._critique_sql_before_execution(state)
        if critique and not self._json_bool(critique.get("passes"), default=True):
            critique_errors = self._string_list(critique.get("errors")) or [
                "SQL critique found that the query may not answer the question."
            ]
            corrected_sql = str(critique.get("corrected_sql") or "").strip()
            corrected_validation = critique.get("corrected_sql_validation") or {}
            if corrected_sql and corrected_validation.get("is_valid"):
                state["sql_query"] = corrected_sql
                state["sql_validation"] = {
                    "is_valid": True,
                    "errors": [],
                    "warnings": [
                        *result.warnings,
                        *self._string_list(critique.get("warnings")),
                        *[
                            f"SQL critic corrected prior query: {error}"
                            for error in critique_errors
                        ],
                    ],
                    "used_tables": corrected_validation.get("used_tables", []),
                    "used_columns": corrected_validation.get("used_columns", {}),
                    "llm_critique": critique,
                }
                add_event(
                    state,
                    "Validating",
                    "completed",
                    "SQL critique supplied a safe corrected query.",
                    warnings=state["sql_validation"]["warnings"],
                )
                return state

            state["sql_validation"]["is_valid"] = False
            state["sql_validation"]["errors"] = critique_errors
            state["sql_validation"]["llm_critique"] = critique
            state["errors"].extend(critique_errors)
            add_event(
                state,
                "Validating",
                "error",
                "SQL critique requested a corrected query.",
                errors=critique_errors,
                corrected_sql=critique.get("corrected_sql") or "",
            )
        else:
            if critique:
                state["sql_validation"]["llm_critique"] = critique
            add_event(
                state, "Validating", "completed", "SQL validation passed.", warnings=result.warnings
            )
        return state

    async def execute_sql(self, state: AgentState) -> AgentState:
        add_event(state, "Executing", "running", "Executing read-only SQL.")
        state.pop("sql_result", None)
        try:
            result = await self.query_engine.execute_sql(
                state["sql_query"], state.get("selected_data_sources")
            )
            state["sql_result"] = {
                "columns": result.columns,
                "rows": result.rows,
                "row_count": result.row_count,
                "truncated": result.truncated,
                "duration_ms": result.duration_ms,
                "metadata": result.metadata,
            }
            add_event(
                state,
                "Executing",
                "completed",
                f"SQL returned {result.row_count} rows.",
                duration_ms=result.duration_ms,
            )
        except Exception as exc:
            state["errors"].append(f"SQL execution failed: {exc}")
            add_event(state, "Executing", "error", "SQL execution failed.", error=str(exc))
        return state

    async def generate_python(self, state: AgentState) -> AgentState:
        state["python_attempts"] = int(state.get("python_attempts", 0)) + 1
        add_event(
            state,
            "Generating code",
            "running",
            f"Generating Python analysis attempt {state['python_attempts']}.",
        )
        prompt = [
            {"role": "system", "content": PYTHON_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": state["user_question"],
                        "schema": state.get("schema_context", ""),
                        "schema_interpretation": state.get("schema_interpretation", {}),
                        "plan": state.get("execution_plan", {}),
                        "recent_messages": state.get("messages", [])[-8:],
                        "sql_attempts": state.get("sql_attempts", 0),
                        "sql_repair_feedback": self._sql_repair_feedback(state),
                        "previous_errors": state.get("errors", [])[-5:],
                    }
                ),
            },
        ]
        try:
            payload = await self.llm.complete_json(prompt)
            state["python_code"] = (payload.get("code") or "").strip()
            if payload.get("reasoning_summary"):
                state["execution_plan"]["python_reasoning_summary"] = payload["reasoning_summary"]
        except Exception as exc:
            state["python_code"] = ""
            state["errors"].append(f"Python generation failed: {exc}")
        add_event(state, "Generating code", "completed", "Python generation finished.")
        return state

    async def validate_python(self, state: AgentState) -> AgentState:
        add_event(state, "Validating", "running", "Validating Python analysis code.")
        result = self.python_guard.validate(state.get("python_code", ""))
        state["python_validation"] = {
            "is_valid": result.is_valid,
            "errors": result.errors,
            "warnings": result.warnings,
        }
        if not result.is_valid:
            state["errors"].extend(result.errors)
            add_event(
                state, "Validating", "error", "Python validation failed.", errors=result.errors
            )
        else:
            add_event(
                state,
                "Validating",
                "completed",
                "Python validation passed.",
                warnings=result.warnings,
            )
        return state

    async def execute_python(self, state: AgentState) -> AgentState:
        add_event(state, "Executing", "running", "Running Python in a constrained sandbox.")
        result = await self.python_sandbox.execute(
            state.get("python_code", ""), state.get("selected_data_sources")
        )
        state["python_result"] = {
            "ok": result.ok,
            "answer": result.answer,
            "stdout": result.stdout,
            "result_table": result.result_table,
            "chart": result.chart,
            "error": result.error,
        }
        if result.ok:
            add_event(state, "Executing", "completed", "Python analysis completed.")
        else:
            state["errors"].append(f"Python execution failed: {result.error}")
            add_event(state, "Executing", "error", "Python execution failed.", error=result.error)
        return state

    async def critique_answer(self, state: AgentState) -> AgentState:
        state["critique_attempts"] = int(state.get("critique_attempts", 0)) + 1
        add_event(
            state,
            "Critiquing answer",
            "running",
            "Checking whether the result answers the question.",
        )
        prompt = [
            {"role": "system", "content": CRITIC_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": state["user_question"],
                        "plan": state.get("execution_plan", {}),
                        "schema": state.get("schema_context", ""),
                        "recent_messages": state.get("messages", [])[-8:],
                        "sql": state.get("sql_query"),
                        "sql_validation": state.get("sql_validation"),
                        "sql_attempts": state.get("sql_attempts", 0),
                        "sql_result_summary": self._sql_result_summary(state),
                        "sql_result_preview": state.get("sql_result", {}).get("rows", [])[:10],
                        "python_code": state.get("python_code"),
                        "python_result": state.get("python_result"),
                        "python_attempts": state.get("python_attempts", 0),
                        "errors": state.get("errors", [])[-5:],
                    }
                ),
            },
        ]
        try:
            critique = await self.llm.complete_json(prompt, max_tokens=1024)
        except Exception as exc:
            critique = {
                "passes": True,
                "confidence": "medium",
                "caveats": [f"Automated LLM critique was unavailable: {exc}"],
                "needs_repair": False,
                "repair_tool": None,
                "summary": "Skipped model critique due to endpoint error.",
            }
        state["critique"] = critique
        status = "completed" if critique.get("passes", True) else "warning"
        add_event(
            state, "Critiquing answer", status, critique.get("summary", "Critique completed.")
        )
        return state

    async def final_response(self, state: AgentState) -> AgentState:
        artifacts = self._build_artifacts(state)
        source_refs = self._build_source_refs(state)
        selected_tool = state.get("execution_plan", {}).get("tool")

        if (
            selected_tool == "metadata"
            or (not selected_tool and state.get("question_type") == "metadata_lookup")
        ):
            final = await self._build_metadata_response(state)
            artifacts = final.pop("artifacts", artifacts)
            source_refs = final.pop("sources", source_refs)

        elif (
            selected_tool == "question_suggestions"
            or (not selected_tool and state.get("question_type") == "question_suggestions")
        ):
            final = await self._build_question_suggestions_response(state)
            artifacts = final.pop("artifacts", artifacts)
            source_refs = final.pop("sources", source_refs)

        elif state.get("execution_plan", {}).get("tool") in {"none", "clarify"}:
            answer = (
                state.get("execution_plan", {}).get("clarification_question")
                or "I cannot answer yet because no usable data sources are configured."
            )
            final = {
                "answer": answer,
                "reasoning_summary": "Checked the request and available metadata before stopping.",
                "caveats": state.get("errors", []),
                "confidence": "low",
            }
        else:
            final = await self._compose_final_with_fallback(state)

        add_event(state, "Finalizing", "running", "Preparing the final response.")
        final.update(
            {
                "sql_query": self._exposed_sql_query(state),
                "python_code": self._exposed_python_code(state),
                "artifacts": artifacts,
                "sources": source_refs,
                "status_events": state.get("status_events", []),
            }
        )
        state["final_response"] = final
        add_event(state, "Finalizing", "completed", "Final response is ready.")
        state["final_response"]["status_events"] = state.get("status_events", [])
        return state

    def route_after_plan(self, state: AgentState) -> str:
        tool = state.get("execution_plan", {}).get("tool", "sql")
        if tool in {"question_suggestions", "metadata"}:
            return "final"
        if (
            tool in {"clarify", "none"}
            or state.get("question_type") in {"ambiguous", "impossible"}
        ):
            return "final"
        if tool == "python":
            return "python"
        if tool == "sql":
            return "sql"
        if state.get("question_type") in {"requires_python", "requires_chart"}:
            return "python"
        return "sql"

    def route_after_sql_validation(self, state: AgentState) -> str:
        if state.get("sql_validation", {}).get("is_valid"):
            return "execute"
        if int(state.get("sql_attempts", 0)) < MAX_SQL_ATTEMPTS:
            return "repair"
        if int(state.get("python_attempts", 0)) < MAX_PYTHON_ATTEMPTS:
            return "python"
        return "final"

    def route_after_sql_execution(self, state: AgentState) -> str:
        if state.get("sql_result"):
            return "critique"
        if int(state.get("sql_attempts", 0)) < MAX_SQL_ATTEMPTS:
            return "repair"
        if int(state.get("python_attempts", 0)) < MAX_PYTHON_ATTEMPTS:
            return "python"
        return "final"

    def route_after_python_validation(self, state: AgentState) -> str:
        if state.get("python_validation", {}).get("is_valid"):
            return "execute"
        if int(state.get("python_attempts", 0)) < MAX_PYTHON_ATTEMPTS:
            return "repair"
        return "final"

    def route_after_python_execution(self, state: AgentState) -> str:
        if state.get("python_result", {}).get("ok"):
            return "critique"
        if int(state.get("python_attempts", 0)) < MAX_PYTHON_ATTEMPTS:
            return "repair"
        return "final"

    def route_after_critique(self, state: AgentState) -> str:
        critique = state.get("critique", {})
        needs_repair = self._json_bool(
            critique.get("needs_repair"), default=False
        ) or not self._json_bool(critique.get("passes"), default=True)
        if needs_repair and int(state.get("critique_attempts", 0)) < MAX_CRITIQUE_ATTEMPTS:
            repair_tool = critique.get("repair_tool")
            if repair_tool == "sql":
                if int(state.get("sql_attempts", 0)) < MAX_SQL_ATTEMPTS:
                    return "sql"
                if int(state.get("python_attempts", 0)) < MAX_PYTHON_ATTEMPTS:
                    return "python"
            if repair_tool == "python":
                if int(state.get("python_attempts", 0)) < MAX_PYTHON_ATTEMPTS:
                    return "python"
                if int(state.get("sql_attempts", 0)) < MAX_SQL_ATTEMPTS:
                    return "sql"
            if int(state.get("sql_attempts", 0)) < MAX_SQL_ATTEMPTS:
                return "sql"
            if int(state.get("python_attempts", 0)) < MAX_PYTHON_ATTEMPTS:
                return "python"
        return "final"

    async def _critique_sql_before_execution(self, state: AgentState) -> dict[str, Any] | None:
        prompt = [
            {"role": "system", "content": SQL_CRITIC_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": state["user_question"],
                        "recent_messages": state.get("messages", [])[-8:],
                        "schema": state.get("schema_context", ""),
                        "schema_interpretation": state.get("schema_interpretation", {}),
                        "plan": state.get("execution_plan", {}),
                        "sql": state.get("sql_query", ""),
                        "attempt": state.get("sql_attempts", 0),
                        "repair_feedback": self._sql_repair_feedback(state),
                    }
                ),
            },
        ]
        try:
            critique = await self.llm.complete_json(prompt, max_tokens=1200)
        except Exception as exc:
            return {
                "passes": True,
                "errors": [],
                "warnings": [f"SQL critique unavailable: {exc}"],
                "corrected_sql": "",
            }

        if not isinstance(critique, dict):
            return {
                "passes": True,
                "errors": [],
                "warnings": ["SQL critique returned an unexpected response shape."],
                "corrected_sql": "",
            }

        if self._json_bool(critique.get("passes"), default=True):
            audit = await self._audit_sql_quality_before_execution(state)
            if audit and not self._json_bool(audit.get("passes"), default=True):
                critique = audit

        corrected_sql = str(critique.get("corrected_sql") or "").strip()
        if corrected_sql:
            corrected_validation = self.sql_guard.validate(
                corrected_sql, state.get("table_columns", {})
            )
            critique["corrected_sql_validation"] = {
                "is_valid": corrected_validation.is_valid,
                "errors": corrected_validation.errors,
                "warnings": corrected_validation.warnings,
                "used_tables": corrected_validation.used_tables,
                "used_columns": corrected_validation.used_columns,
            }
            if not corrected_validation.is_valid:
                critique["errors"] = [
                    *self._string_list(critique.get("errors")),
                    *[
                        f"Suggested correction is invalid: {error}"
                        for error in corrected_validation.errors
                    ],
                ]
        return critique

    async def _audit_sql_quality_before_execution(
        self, state: AgentState
    ) -> dict[str, Any] | None:
        prompt = [
            {"role": "system", "content": SQL_QUALITY_AUDIT_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": state["user_question"],
                        "recent_messages": state.get("messages", [])[-8:],
                        "schema": state.get("schema_context", ""),
                        "schema_interpretation": state.get("schema_interpretation", {}),
                        "plan": state.get("execution_plan", {}),
                        "sql": state.get("sql_query", ""),
                        "attempt": state.get("sql_attempts", 0),
                        "repair_feedback": self._sql_repair_feedback(state),
                    }
                ),
            },
        ]
        try:
            audit = await self.llm.complete_json(prompt, max_tokens=1200)
        except Exception as exc:
            return {
                "passes": True,
                "errors": [],
                "warnings": [f"SQL quality audit unavailable: {exc}"],
                "corrected_sql": "",
            }

        if not isinstance(audit, dict):
            return {
                "passes": True,
                "errors": [],
                "warnings": ["SQL quality audit returned an unexpected response shape."],
                "corrected_sql": "",
            }
        return audit

    @staticmethod
    def _json_bool(value: Any, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "1"}:
                return True
            if normalized in {"false", "no", "0"}:
                return False
        return default

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if value is None:
            return []
        items = value if isinstance(value, list) else [value]
        return [str(item).strip() for item in items if str(item).strip()]

    @staticmethod
    def _sql_result_summary(state: AgentState) -> dict[str, Any] | None:
        result = state.get("sql_result")
        if not result:
            return None
        return {
            "columns": result.get("columns", []),
            "row_count": result.get("row_count", 0),
            "truncated": result.get("truncated", False),
            "duration_ms": result.get("duration_ms"),
        }

    def _sql_repair_feedback(self, state: AgentState) -> dict[str, Any] | None:
        has_feedback = any(
            [
                state.get("sql_query"),
                state.get("sql_validation"),
                state.get("sql_result"),
                state.get("critique"),
                state.get("errors"),
            ]
        )
        if not has_feedback:
            return None
        return {
            "failed_or_prior_sql": state.get("sql_query"),
            "sql_validation": state.get("sql_validation"),
            "sql_result_summary": self._sql_result_summary(state),
            "sql_result_preview": state.get("sql_result", {}).get("rows", [])[:5],
            "critique": state.get("critique"),
            "recent_errors": state.get("errors", [])[-8:],
        }

    @staticmethod
    def _fallback_classification(question: str) -> dict[str, Any]:
        return {"question_type": "sql_answerable", "requires_chart": False}

    @staticmethod
    def _fallback_plan(question: str, question_type: str) -> dict[str, Any]:
        if question_type == "question_suggestions":
            return DataChatAgent._question_suggestions_plan()
        if question_type == "metadata_lookup":
            return DataChatAgent._metadata_plan()
        if question_type in {"requires_python", "requires_chart"}:
            return {
                "tool": "python",
                "steps": ["Inspect schema", "Run constrained Python analysis", "Summarize result"],
                "requires_chart": question_type == "requires_chart",
                "clarification_question": None,
            }
        return {
            "tool": "sql",
            "steps": [
                "Inspect schema",
                "Generate read-only SQL",
                "Validate and execute",
                "Summarize result",
            ],
            "requires_chart": False,
            "clarification_question": None,
        }

    async def resolve_ambiguity_with_schema(self, state: AgentState) -> None:
        add_event(
            state,
            "Planning",
            "running",
            "Asking the LLM to resolve ambiguous wording against the current schema.",
        )
        prompt = [
            {"role": "system", "content": AMBIGUITY_RESOLVER_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": state["user_question"],
                        "classification": state.get("classification", {}),
                        "schema": state.get("schema_context", ""),
                        "recent_messages": state.get("messages", [])[-8:],
                    }
                ),
            },
        ]
        try:
            interpretation = await self.llm.complete_json(prompt, max_tokens=1400)
        except Exception as exc:
            interpretation = {
                "question_type": "ambiguous",
                "resolved_question": None,
                "selected_tables": [],
                "selected_columns": [],
                "clarification_question": (
                    "I can help with that, but I need one more detail first: which "
                    "table, metric, time period, or grouping should I use?"
                ),
                "reasoning_summary": f"LLM schema interpretation failed: {exc}",
            }
            state["errors"].append(f"Ambiguity resolution failed: {exc}")

        self._apply_schema_interpretation(state, interpretation)
        if state.get("question_type") == "ambiguous":
            add_event(
                state,
                "Planning",
                "warning",
                "LLM schema interpretation still needs clarification.",
            )
        else:
            add_event(
                state,
                "Planning",
                "completed",
                f"LLM resolved request as {state['question_type']}.",
            )

    @staticmethod
    def _apply_schema_interpretation(state: AgentState, payload: dict[str, Any]) -> None:
        allowed_question_types = {
            "question_suggestions",
            "metadata_lookup",
            "sql_answerable",
            "requires_python",
            "requires_chart",
            "ambiguous",
            "impossible",
        }
        question_type = str(payload.get("question_type") or "ambiguous").strip()
        if question_type not in allowed_question_types:
            question_type = "ambiguous"

        interpretation = {
            "question_type": question_type,
            "resolved_question": payload.get("resolved_question"),
            "selected_tables": payload.get("selected_tables") or [],
            "selected_columns": payload.get("selected_columns") or [],
            "clarification_question": payload.get("clarification_question"),
            "reasoning_summary": payload.get("reasoning_summary") or "",
        }
        state["schema_interpretation"] = interpretation
        state["question_type"] = question_type
        state.setdefault("classification", {})["question_type"] = question_type
        if interpretation["clarification_question"]:
            state["classification"]["clarification_question"] = interpretation[
                "clarification_question"
            ]

    @staticmethod
    def _metadata_plan() -> dict[str, Any]:
        return {
            "tool": "metadata",
            "steps": [
                "Inspect current metadata catalog",
                "Summarize configured sources, tables or sheets, columns, row counts, and samples",
                "List known or inferred relationships when available",
            ],
            "requires_chart": False,
            "clarification_question": None,
        }

    @staticmethod
    def _question_suggestions_plan() -> dict[str, Any]:
        return {
            "tool": "question_suggestions",
            "steps": [
                "Inspect current metadata catalog",
                "Ask the LLM to generate schema-grounded question ideas",
                "Critique the suggestions against available tables and columns",
                "Return polished examples with likely outputs",
            ],
            "requires_chart": False,
            "clarification_question": None,
        }

    @staticmethod
    def _clarification_plan(state: AgentState) -> dict[str, Any]:
        classification = state.get("classification", {})
        question = classification.get("clarification_question") or classification.get("question")
        return {
            "tool": "clarify",
            "steps": ["Ask the user for the missing metric, table, filter, or time period."],
            "requires_chart": False,
            "clarification_question": question
            or (
                "I can help with that, but I need one more detail first: which table, "
                "metric, time period, or grouping should I use?"
            ),
        }

    async def _build_question_suggestions_response(self, state: AgentState) -> dict[str, Any]:
        schema = await self.catalog.get_schema(state.get("selected_data_sources"))
        schema_payload = self._friendly_schema_payload(schema)
        add_event(
            state,
            "Generating answer",
            "running",
            "Asking the LLM for schema-grounded question suggestions.",
        )
        prompt = [
            {"role": "system", "content": QUESTION_SUGGESTIONS_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_question": state.get("user_question"),
                        "schema": schema_payload,
                        "recent_messages": state.get("messages", [])[-6:],
                    }
                ),
            },
        ]
        try:
            generated = await self.llm.complete_json(prompt, max_tokens=2400)
        except Exception as exc:
            add_event(
                state,
                "Generating answer",
                "error",
                "LLM question suggestion generation failed.",
                error=str(exc),
            )
            return {
                "answer": (
                    "I could not generate schema-grounded question suggestions because the "
                    "model endpoint was unavailable."
                ),
                "reasoning_summary": (
                    "Inspected the schema, but the LLM did not return suggested questions."
                ),
                "caveats": [str(exc)],
                "confidence": "low",
                "artifacts": [],
                "sources": [],
            }

        generated = self._normalize_question_suggestion_payload(generated)
        add_event(
            state,
            "Generating answer",
            "completed",
            f"Generated {len(generated.get('questions', []))} suggested question(s).",
        )

        add_event(
            state,
            "Critiquing answer",
            "running",
            "Checking suggested questions against the available schema.",
        )
        critique_prompt = [
            {"role": "system", "content": QUESTION_SUGGESTIONS_CRITIC_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_question": state.get("user_question"),
                        "schema": schema_payload,
                        "draft": generated,
                    }
                ),
            },
        ]
        try:
            critique = await self.llm.complete_json(critique_prompt, max_tokens=2400)
        except Exception as exc:
            critique = {
                "passes": True,
                "confidence": generated.get("confidence", "medium"),
                "summary": f"Critique model was unavailable: {exc}",
                "caveats": [f"Automated critique was unavailable: {exc}"],
                "revised_answer": None,
                "revised_questions": [],
            }

        if critique.get("revised_answer"):
            generated["answer"] = critique["revised_answer"]
        if critique.get("revised_questions"):
            generated["questions"] = self._clean_question_rows(critique["revised_questions"])
        caveats = [
            *self._unique_strings(generated.get("caveats") or []),
            *self._unique_strings(critique.get("caveats") or []),
        ]
        caveats = self._unique_strings(caveats)
        confidence = critique.get("confidence") or generated.get("confidence") or "medium"
        state["critique"] = {
            "passes": bool(critique.get("passes", True)),
            "confidence": confidence,
            "caveats": caveats,
            "summary": critique.get("summary", "Question suggestions reviewed."),
            "needs_repair": False,
            "repair_tool": None,
        }
        add_event(
            state,
            "Critiquing answer",
            "completed" if critique.get("passes", True) else "warning",
            state["critique"]["summary"],
        )

        questions = self._clean_question_rows(generated.get("questions", []))
        answer = self._format_question_suggestion_answer(generated.get("answer", ""), questions)
        artifacts = []
        if questions:
            artifacts.append(
                {
                    "type": "table",
                    "title": "Suggested Questions",
                    "columns": ["Category", "Question", "Why it helps", "Likely tables", "Output"],
                    "rows": questions[: self.settings.sql_preview_row_limit],
                    "truncated": len(questions) > self.settings.sql_preview_row_limit,
                }
            )

        return {
            "answer": answer,
            "reasoning_summary": (
                "Used the current metadata catalog as context, asked the LLM to generate "
                "question ideas, then critiqued the suggestions against the available schema."
            ),
            "caveats": caveats,
            "confidence": confidence if confidence in {"low", "medium", "high"} else "medium",
            "artifacts": artifacts,
            "sources": [],
        }

    @staticmethod
    def _format_question_suggestion_answer(intro: str, questions: list[dict[str, Any]]) -> str:
        lines = [intro.strip()] if intro and intro.strip() else []
        if not questions:
            return "\n\n".join(lines) or "I could not generate supported question ideas."

        if lines:
            lines.append("")
        lines.append("Here are specific questions you can ask:")
        for row in questions[:10]:
            category = row.get("Category", "Analysis")
            question = row.get("Question", "")
            output = row.get("Output", "narrative")
            lines.append(f"- {category}: {question} ({output})")
        lines.append("")
        lines.append(
            "I also included a table below with why each question is useful and which "
            "tables it uses."
        )
        return "\n".join(lines)

    @staticmethod
    def _friendly_schema_payload(schema: Any) -> dict[str, Any]:
        source_by_id = {source.id: source for source in schema.data_sources}
        tables = []
        for table in schema.tables:
            source = source_by_id.get(table.data_source_id)
            tables.append(
                {
                    "source": DataChatAgent._friendly_name(
                        source.name if source else table.data_source_id
                    ),
                    "source_type": source.source_type if source else "",
                    "table": table.original_name,
                    "kind": table.kind,
                    "row_count": table.row_count,
                    "columns": [
                        {
                            "name": column.original_name,
                            "type": column.data_type,
                            "sample_values": column.sample_values[:8],
                        }
                        for column in table.columns
                    ],
                    "sample_rows": table.sample_rows[:5],
                }
            )
        display_names = {table.canonical_name: table.original_name for table in schema.tables}
        relationships = [
            {
                "left_table": display_names.get(rel.left_table, rel.left_table),
                "left_column": rel.left_column,
                "right_table": display_names.get(rel.right_table, rel.right_table),
                "right_column": rel.right_column,
                "confidence": rel.confidence,
                "evidence": rel.evidence,
            }
            for rel in schema.relationships
        ]
        return {"tables": tables, "relationships": relationships}

    @staticmethod
    def _unique_strings(values: list[Any]) -> list[str]:
        unique = []
        seen = set()
        for value in values:
            rendered = str(value)
            if rendered in seen:
                continue
            seen.add(rendered)
            unique.append(rendered)
        return unique

    @staticmethod
    def _normalize_question_suggestion_payload(payload: dict[str, Any]) -> dict[str, Any]:
        payload["questions"] = DataChatAgent._clean_question_rows(payload.get("questions", []))
        if payload.get("confidence") not in {"low", "medium", "high"}:
            payload["confidence"] = "medium"
        if not isinstance(payload.get("caveats"), list):
            payload["caveats"] = []
        return payload

    @staticmethod
    def _clean_question_rows(rows: Any) -> list[dict[str, Any]]:
        cleaned = []
        if not isinstance(rows, list):
            return cleaned
        for row in rows:
            if not isinstance(row, dict):
                continue
            likely_tables = row.get("likely_tables") or row.get("Likely tables") or []
            if isinstance(likely_tables, str):
                likely_tables = [item.strip() for item in likely_tables.split(",") if item.strip()]
            cleaned.append(
                {
                    "Category": str(row.get("category") or row.get("Category") or "Analysis"),
                    "Question": str(row.get("question") or row.get("Question") or "").strip(),
                    "Why it helps": str(row.get("why") or row.get("Why it helps") or "").strip(),
                    "Likely tables": ", ".join(str(item) for item in likely_tables),
                    "Output": str(row.get("output") or row.get("Output") or "narrative"),
                }
            )
        return [row for row in cleaned if row["Question"]]

    async def _build_metadata_response(self, state: AgentState) -> dict[str, Any]:
        schema = await self.catalog.get_schema(state.get("selected_data_sources"))
        tables = schema.tables
        table_count = len(tables)
        source_count = len(schema.data_sources)
        known_row_counts = [table.row_count for table in tables if table.row_count is not None]
        total_rows = sum(known_row_counts)

        if table_count == 0:
            caveats = ["No queryable tables or sheets were found in the current metadata catalog."]
            if source_count:
                caveats.append("Rescan the data sources if files were added or changed recently.")
            return {
                "answer": (
                    f"I found {source_count} configured data source(s), but no queryable "
                    "tables or sheets are available yet."
                ),
                "reasoning_summary": (
                    "Inspected the current metadata catalog without generating SQL or Python."
                ),
                "caveats": caveats,
                "confidence": "low",
                "artifacts": [],
                "sources": [],
            }

        caveats = []
        if len(known_row_counts) != table_count:
            caveats.append("Some tables do not have row counts in the current metadata scan.")
        if any(source.status != "active" for source in schema.data_sources):
            caveats.append("One or more configured data sources are not active.")
        caveats.append("If files changed since the last scan, rescan before relying on row counts.")

        schema_payload = self._friendly_schema_payload(schema)
        add_event(
            state,
            "Generating answer",
            "running",
            "Asking the LLM to summarize the current metadata catalog.",
        )
        overview_prompt = [
            {"role": "system", "content": METADATA_OVERVIEW_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_question": state.get("user_question"),
                        "source_count": source_count,
                        "table_count": table_count,
                        "known_total_rows": (
                            total_rows
                            if known_row_counts and len(known_row_counts) == table_count
                            else None
                        ),
                        "schema": schema_payload,
                        "recent_messages": state.get("messages", [])[-6:],
                    }
                ),
            },
        ]
        try:
            generated = await self.llm.complete_json(overview_prompt, max_tokens=2200)
        except Exception as exc:
            add_event(
                state,
                "Generating answer",
                "error",
                "LLM metadata overview generation failed.",
                error=str(exc),
            )
            return {
                "answer": (
                    "I inspected the metadata catalog, but the model endpoint was unavailable "
                    "before it could write a grounded overview."
                ),
                "reasoning_summary": (
                    "Retrieved the current metadata catalog, but the LLM overview step failed."
                ),
                "caveats": [str(exc), *caveats],
                "confidence": "low",
                "artifacts": [],
                "sources": [],
            }

        add_event(state, "Generating answer", "completed", "LLM metadata overview generated.")
        generated_caveats = (
            generated.get("caveats") if isinstance(generated.get("caveats"), list) else []
        )
        confidence = generated.get("confidence") if generated.get("confidence") in {
            "low",
            "medium",
            "high",
        } else "medium"

        add_event(
            state,
            "Critiquing answer",
            "running",
            "Checking the metadata overview against the available schema.",
        )
        critique_prompt = [
            {"role": "system", "content": METADATA_OVERVIEW_CRITIC_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_question": state.get("user_question"),
                        "schema": schema_payload,
                        "draft": generated,
                    }
                ),
            },
        ]
        try:
            critique = await self.llm.complete_json(critique_prompt, max_tokens=1800)
        except Exception as exc:
            critique = {
                "passes": True,
                "confidence": confidence,
                "summary": f"Critique model was unavailable: {exc}",
                "caveats": [f"Automated critique was unavailable: {exc}"],
                "revised_answer": generated.get("answer"),
            }

        answer = str(critique.get("revised_answer") or generated.get("answer") or "").strip()
        all_caveats = self._unique_strings(
            [
                *generated_caveats,
                *self._string_list(critique.get("caveats")),
                *caveats,
            ]
        )
        confidence = critique.get("confidence") or confidence
        if confidence not in {"low", "medium", "high"}:
            confidence = "medium"
        state["critique"] = {
            "passes": self._json_bool(critique.get("passes"), default=True),
            "confidence": confidence,
            "caveats": all_caveats,
            "summary": critique.get("summary", "Metadata overview reviewed."),
            "needs_repair": False,
            "repair_tool": None,
        }
        add_event(
            state,
            "Critiquing answer",
            "completed" if state["critique"]["passes"] else "warning",
            state["critique"]["summary"],
        )

        return {
            "answer": answer
            or "I inspected the metadata catalog but could not compose an overview.",
            "reasoning_summary": (
                "Used the current metadata catalog as LLM context and critiqued the overview "
                "against the available sources, tables, columns, samples, and relationships."
            ),
            "caveats": all_caveats,
            "confidence": confidence,
            "artifacts": [],
            "sources": [],
        }

    @staticmethod
    def _friendly_name(value: str) -> str:
        cleaned = value.removeprefix("example_").replace("_", " ").strip()
        return cleaned.title() if cleaned else value

    def _build_artifacts(self, state: AgentState) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        python_result = state.get("python_result", {})
        prefer_python = bool(
            python_result.get("ok")
            and (python_result.get("result_table") or python_result.get("chart"))
        )
        sql_result = state.get("sql_result", {})
        if not prefer_python and sql_result.get("columns"):
            artifacts.append(
                {
                    "type": "table",
                    "title": "SQL result",
                    "columns": sql_result.get("columns", []),
                    "rows": sql_result.get("rows", [])[: self.settings.sql_preview_row_limit],
                    "truncated": sql_result.get("truncated", False),
                }
            )
        if python_result.get("result_table"):
            rows = python_result["result_table"]
            columns = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
            artifacts.append(
                {
                    "type": "table",
                    "title": "Python analysis result",
                    "columns": columns,
                    "rows": rows[: self.settings.sql_preview_row_limit],
                    "truncated": len(rows) > self.settings.sql_preview_row_limit,
                }
            )
        if python_result.get("chart"):
            artifacts.append(
                {"type": "chart", "title": "Analysis chart", "spec": python_result["chart"]}
            )
        return artifacts

    @staticmethod
    def _build_source_refs(state: AgentState) -> list[dict[str, Any]]:
        if state.get("python_result", {}).get("ok"):
            return []
        validation = state.get("sql_validation", {})
        used_tables = validation.get("used_tables") or []
        used_columns = validation.get("used_columns") or {}
        return [{"table": table, "columns": used_columns.get(table, [])} for table in used_tables]

    @staticmethod
    def _exposed_sql_query(state: AgentState) -> str | None:
        sql_query = (state.get("sql_query") or "").strip()
        return sql_query or None

    @staticmethod
    def _exposed_python_code(state: AgentState) -> str | None:
        python_code = (state.get("python_code") or "").strip()
        return python_code or None

    async def _compose_final_with_fallback(self, state: AgentState) -> dict[str, Any]:
        python_answer = state.get("python_result", {}).get("answer")
        if python_answer:
            return {
                "answer": python_answer,
                "reasoning_summary": state.get("execution_plan", {}).get(
                    "python_reasoning_summary",
                    "Ran sandboxed Python analysis over approved tables.",
                ),
                "caveats": state.get("critique", {}).get("caveats", []),
                "confidence": self._bounded_confidence(
                    state.get("critique", {}).get("confidence"),
                    state.get("critique", {}),
                ),
            }

        prompt = [
            {"role": "system", "content": FINAL_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": state["user_question"],
                        "plan": state.get("execution_plan", {}),
                        "sql": state.get("sql_query"),
                        "sql_result": state.get("sql_result"),
                        "python_result": state.get("python_result"),
                        "critique": state.get("critique", {}),
                        "errors": self._active_errors_for_final(state),
                    }
                ),
            },
        ]
        try:
            final = await self.llm.complete_json(prompt, max_tokens=2048)
            return {
                "answer": final.get("answer") or self._fallback_answer(state),
                "reasoning_summary": final.get("reasoning_summary")
                or "Executed the validated plan.",
                "caveats": final.get("caveats") or state.get("critique", {}).get("caveats", []),
                "confidence": self._bounded_confidence(
                    final.get("confidence"),
                    state.get("critique", {}),
                ),
            }
        except Exception as exc:
            caveats = state.get("critique", {}).get("caveats", [])
            caveats.append(f"Final model summary was unavailable: {exc}")
            return {
                "answer": self._fallback_answer(state),
                "reasoning_summary": "Used validated execution results and a fallback summarizer.",
                "caveats": caveats,
                "confidence": self._bounded_confidence(None, state.get("critique", {})),
            }

    @staticmethod
    def _bounded_confidence(candidate: Any, critique: dict[str, Any]) -> str:
        order = {"low": 0, "medium": 1, "high": 2}
        candidate_text = str(candidate or "").strip().lower()
        critique_text = str(critique.get("confidence") or "").strip().lower()
        confidence = candidate_text if candidate_text in order else critique_text
        if confidence not in order:
            confidence = "medium"

        if not DataChatAgent._json_bool(critique.get("passes"), default=True):
            return "low"

        if critique_text in order and order[confidence] > order[critique_text]:
            return critique_text
        return confidence

    @staticmethod
    def _active_errors_for_final(state: AgentState) -> list[str]:
        critique_passes = DataChatAgent._json_bool(
            state.get("critique", {}).get("passes"), default=True
        )
        if critique_passes and (
            state.get("sql_result")
            or state.get("python_result", {}).get("ok")
        ):
            return []
        return state.get("errors", [])[-5:]

    @staticmethod
    def _fallback_answer(state: AgentState) -> str:
        sql_result = state.get("sql_result", {})
        rows = sql_result.get("rows") or []
        columns = sql_result.get("columns") or []
        if rows:
            row_count = sql_result.get("row_count", len(rows))
            aggregate_columns = DataChatAgent._aggregate_result_columns(columns)
            preview = DataChatAgent._format_fallback_rows(rows[:3], columns)
            if aggregate_columns:
                metric_text = ", ".join(aggregate_columns[:3])
                return (
                    f"The result table contains {row_count} grouped result row(s) with "
                    f"aggregate metric(s): {metric_text}. Top rows shown include: {preview}."
                )
            return (
                f"The query returned {row_count} result row(s) with columns "
                f"{', '.join(columns[:8])}. First rows shown include: {preview}."
            )
        if state.get("python_result", {}).get("stdout"):
            return state["python_result"]["stdout"].strip()
        if state.get("errors"):
            return (
                "I could not complete the analysis safely. "
                "See caveats for the validation or execution errors."
            )
        return "The analysis completed, but no rows were returned."

    @staticmethod
    def _aggregate_result_columns(columns: list[str]) -> list[str]:
        aggregate_tokens = (
            "count",
            "total",
            "sum",
            "avg",
            "average",
            "mean",
            "median",
            "min",
            "max",
            "pct",
            "percent",
            "percentage",
            "share",
            "rate",
        )
        return [
            column
            for column in columns
            if any(token in column.lower() for token in aggregate_tokens)
        ]

    @staticmethod
    def _format_fallback_rows(rows: list[dict[str, Any]], columns: list[str]) -> str:
        formatted_rows: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                formatted_rows.append(str(row))
                continue
            visible_columns = columns[:6] if columns else list(row.keys())[:6]
            cells = [
                f"{column}={row.get(column)}"
                for column in visible_columns
                if column in row and row.get(column) is not None
            ]
            formatted_rows.append("; ".join(cells))
        return " | ".join(formatted_rows)
