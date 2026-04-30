from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import (
    CLASSIFIER_SYSTEM,
    CRITIC_SYSTEM,
    FINAL_SYSTEM,
    PLANNER_SYSTEM,
    PYTHON_SYSTEM,
    QUESTION_SUGGESTIONS_CRITIC_SYSTEM,
    QUESTION_SUGGESTIONS_SYSTEM,
    SQL_SYSTEM,
)
from app.agent.python_guard import PythonGuard
from app.agent.python_sandbox import PythonSandbox
from app.agent.sql_guard import SqlGuard
from app.agent.state import AgentState
from app.core.config import get_settings
from app.core.llm import LLMClient
from app.datasources.catalog import DataSourceCatalog
from app.datasources.query_engine import QueryEngine


def status_event(step: str, status: str, message: str, **metadata: Any) -> dict[str, Any]:
    return {
        "step": step,
        "status": status,
        "message": message,
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
            {"execute": "execute_sql", "repair": "generate_sql", "final": "final_response"},
        )
        graph.add_conditional_edges(
            "execute_sql",
            self.route_after_sql_execution,
            {"critique": "critique_answer", "repair": "generate_sql", "final": "final_response"},
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
        if self._is_question_suggestion_request(state):
            classification = {
                "question_type": "question_suggestions",
                "requires_chart": False,
                "reasoning_summary": (
                    "Detected a request for suggested questions grounded in the schema."
                ),
            }
            state["classification"] = classification
            state["question_type"] = "question_suggestions"
            add_event(state, "Planning", "completed", "Classified as question_suggestions.")
            return state

        if self._is_metadata_request(state):
            classification = {
                "question_type": "metadata_lookup",
                "requires_chart": False,
                "reasoning_summary": (
                    "Detected a broad data-catalog request from the question and recent context."
                ),
            }
            state["classification"] = classification
            state["question_type"] = "metadata_lookup"
            add_event(state, "Planning", "completed", "Classified as metadata_lookup.")
            return state

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

        if (
            state.get("question_type") == "question_suggestions"
            or self._is_question_suggestion_request(state)
        ):
            state["execution_plan"] = self._question_suggestions_plan()
            add_event(state, "Planning", "completed", "Plan selected LLM question suggestions.")
            return state

        if state.get("question_type") == "metadata_lookup" or self._is_metadata_request(state):
            state["execution_plan"] = self._metadata_plan()
            add_event(state, "Planning", "completed", "Plan selected metadata catalog summary.")
            return state

        if self._is_numeric_extrema_request(state):
            state["execution_plan"] = self._numeric_extrema_plan()
            add_event(state, "Planning", "completed", "Plan selected numeric extrema profiling.")
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
                    }
                ),
            },
        ]
        try:
            plan = await self.llm.complete_json(prompt)
        except Exception as exc:
            plan = self._fallback_plan(state["user_question"], state.get("question_type", ""))
            plan["llm_warning"] = str(exc)
        state["execution_plan"] = plan
        add_event(
            state, "Planning", "completed", f"Plan selected {plan.get('tool', 'sql')} execution."
        )
        return state

    async def generate_sql(self, state: AgentState) -> AgentState:
        state["sql_attempts"] = int(state.get("sql_attempts", 0)) + 1
        add_event(
            state,
            "Generating query",
            "running",
            f"Generating SQL attempt {state['sql_attempts']}.",
        )
        prompt = [
            {"role": "system", "content": SQL_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": state["user_question"],
                        "schema": state.get("schema_context", ""),
                        "plan": state.get("execution_plan", {}),
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
        else:
            add_event(
                state, "Validating", "completed", "SQL validation passed.", warnings=result.warnings
            )
        return state

    async def execute_sql(self, state: AgentState) -> AgentState:
        add_event(state, "Executing", "running", "Executing read-only SQL.")
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
                        "plan": state.get("execution_plan", {}),
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
                        "sql": state.get("sql_query"),
                        "sql_result_preview": state.get("sql_result", {}).get("rows", [])[:10],
                        "python_code": state.get("python_code"),
                        "python_result": state.get("python_result"),
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

        if (
            state.get("execution_plan", {}).get("tool") == "metadata"
            or state.get("question_type") == "metadata_lookup"
        ):
            final = await self._build_metadata_response(state)
            artifacts = final.pop("artifacts", artifacts)
            source_refs = final.pop("sources", source_refs)

        elif (
            state.get("execution_plan", {}).get("tool") == "question_suggestions"
            or state.get("question_type") == "question_suggestions"
        ):
            final = await self._build_question_suggestions_response(state)
            artifacts = final.pop("artifacts", artifacts)
            source_refs = final.pop("sources", source_refs)

        elif state.get("execution_plan", {}).get("tool") == "numeric_profile":
            final = await self._build_numeric_extrema_response(state)
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
                "sql_query": state.get("sql_query") or None,
                "python_code": state.get("python_code") or None,
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
        if tool in {"question_suggestions", "metadata", "numeric_profile"}:
            return "final"
        if tool == "python" or state.get("question_type") in {"requires_python", "requires_chart"}:
            return "python"
        if (
            tool in {"clarify", "none"}
            or state.get("question_type") in {"ambiguous", "impossible"}
        ):
            return "final"
        return "sql"

    def route_after_sql_validation(self, state: AgentState) -> str:
        if state.get("sql_validation", {}).get("is_valid"):
            return "execute"
        if int(state.get("sql_attempts", 0)) < 2:
            return "repair"
        return "final"

    def route_after_sql_execution(self, state: AgentState) -> str:
        if state.get("sql_result"):
            return "critique"
        if int(state.get("sql_attempts", 0)) < 2:
            return "repair"
        return "final"

    def route_after_python_validation(self, state: AgentState) -> str:
        if state.get("python_validation", {}).get("is_valid"):
            return "execute"
        if int(state.get("python_attempts", 0)) < 2:
            return "repair"
        return "final"

    def route_after_python_execution(self, state: AgentState) -> str:
        if state.get("python_result", {}).get("ok"):
            return "critique"
        if int(state.get("python_attempts", 0)) < 2:
            return "repair"
        return "final"

    def route_after_critique(self, state: AgentState) -> str:
        critique = state.get("critique", {})
        if (
            critique.get("needs_repair")
            and int(state.get("critique_attempts", 0)) < 2
            and critique.get("repair_tool") in {"sql", "python"}
        ):
            return critique["repair_tool"]
        return "final"

    @staticmethod
    def _fallback_classification(question: str) -> dict[str, Any]:
        if DataChatAgent._is_question_suggestion_request(question):
            return {"question_type": "question_suggestions", "requires_chart": False}
        if DataChatAgent._looks_like_metadata_lookup(question):
            return {"question_type": "metadata_lookup", "requires_chart": False}
        lowered = question.lower()
        if any(term in lowered for term in ("chart", "plot", "visual", "trend", "forecast")):
            return {"question_type": "requires_chart", "requires_chart": True}
        if any(term in lowered for term in ("correlation", "regression", "anomaly", "outlier")):
            return {"question_type": "requires_python", "requires_chart": False}
        return {"question_type": "sql_answerable", "requires_chart": False}

    @staticmethod
    def _fallback_plan(question: str, question_type: str) -> dict[str, Any]:
        if (
            question_type == "question_suggestions"
            or DataChatAgent._is_question_suggestion_request(question)
        ):
            return DataChatAgent._question_suggestions_plan()
        if (
            question_type == "metadata_lookup"
            or DataChatAgent._looks_like_metadata_lookup(question)
        ):
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

    def _is_metadata_request(self, state: AgentState) -> bool:
        question = state.get("user_question", "")
        if self._looks_like_metadata_lookup(question):
            return True
        if self._is_affirmative_followup(question):
            return self._recent_context_requested_metadata(state.get("messages", []))
        return self._looks_like_table_overview(question, state.get("table_columns", {}))

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
    def _numeric_extrema_plan() -> dict[str, Any]:
        return {
            "tool": "numeric_profile",
            "steps": [
                "Inspect current metadata catalog",
                "Find numeric measure columns across active tables",
                "Execute a safe read-only aggregate query for minimum, maximum, and average values",
                "Summarize the highest values with a table and chart",
            ],
            "requires_chart": True,
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

    @classmethod
    def _is_question_suggestion_request(cls, state: AgentState | str) -> bool:
        question = state if isinstance(state, str) else state.get("user_question", "")
        text = cls._normalize_text(question)
        if not text:
            return False
        exact = {
            "what can i ask",
            "what can i ask about",
            "what questions can i ask",
            "what should i ask",
            "suggest questions",
            "suggest some questions",
            "give me questions",
            "give me example questions",
            "show example questions",
            "sample questions",
            "example questions",
            "recommended questions",
            "recommended analyses",
            "analysis ideas",
            "question ideas",
        }
        if text in exact:
            return True
        phrases = (
            "questions can i ask",
            "can i ask about",
            "what analyses can",
            "what analysis can",
            "suggest questions",
            "suggest queries",
            "suggest analyses",
            "example questions",
            "example prompts",
            "sample questions",
            "question ideas",
            "questions should i ask",
            "what should i analyze",
            "what can you analyze",
            "what insights can",
        )
        return any(phrase in text for phrase in phrases)

    def _is_numeric_extrema_request(self, state: AgentState) -> bool:
        text = self._normalize_text(state.get("user_question", ""))
        if not text or self._looks_like_metadata_lookup(text):
            return False
        tokens = set(text.split())
        extrema_terms = {
            "max",
            "maximum",
            "maximums",
            "min",
            "minimum",
            "minimums",
            "highest",
            "lowest",
            "largest",
            "smallest",
            "peak",
            "peaks",
            "extreme",
            "extremes",
        }
        if not tokens & extrema_terms:
            return False
        generic_metric_terms = {
            "value",
            "values",
            "number",
            "numbers",
            "numeric",
            "measure",
            "measures",
        }
        extrema_phrases = (
            "max values",
            "maximum values",
            "maximum value",
            "highest values",
            "largest values",
            "min values",
            "minimum values",
            "lowest values",
            "smallest values",
        )
        return (
            any(phrase in text for phrase in extrema_phrases)
            or bool(tokens & generic_metric_terms)
            or len(tokens) <= 8
        )

    @classmethod
    def _looks_like_metadata_lookup(cls, question: str) -> bool:
        text = cls._normalize_text(question)
        if not text:
            return False
        if cls._is_affirmative_followup(text):
            return False
        exact_metadata_requests = {
            "data",
            "tables",
            "table",
            "schema",
            "columns",
            "sources",
            "source",
            "datasets",
            "dataset",
            "overview",
            "summary",
            "help",
            "give me an overview",
            "give me context",
            "give me a summary",
            "orient me",
            "start",
            "what am i looking at",
            "what are we looking at",
            "what do we have",
            "what is available",
            "what is here",
            "what s here",
            "whats here",
            "what s in here",
            "whats in here",
            "show me around",
        }
        if text in exact_metadata_requests:
            return True

        metadata_phrases = (
            "available data",
            "data available",
            "data catalog",
            "data dictionary",
            "data source",
            "data sources",
            "dataset overview",
            "datasets available",
            "describe the data",
            "describe tables",
            "explain the data",
            "explain these tables",
            "list columns",
            "list sources",
            "list tables",
            "look at the data",
            "sample data",
            "show columns",
            "show me what is available",
            "show me what you have",
            "show sources",
            "show tables",
            "source list",
            "summarize data",
            "table list",
            "tell me about the data",
            "tell me what is here",
            "tell me what s here",
            "walk me through the data",
            "walk me through this",
            "what are these files",
            "what are these tables",
            "what data",
            "what do these files contain",
            "what do these tables contain",
            "what information is available",
            "what is in the data",
            "what is in the tables",
            "what is inside",
            "what is this data about",
            "what is the data",
            "what tables",
            "which columns",
            "which data",
            "which datasets",
            "which sources",
            "which tables",
        )
        if any(phrase in text for phrase in metadata_phrases):
            return True
        if (
            text.startswith("tell me about ")
            and len(text.split()) <= 7
            and not cls._looks_like_analytical_request(text)
        ):
            return True

        tokens = set(text.split())
        metadata_terms = {
            "catalog",
            "column",
            "columns",
            "data",
            "database",
            "databases",
            "dataset",
            "datasets",
            "dictionary",
            "file",
            "files",
            "schema",
            "sheet",
            "sheets",
            "source",
            "sources",
            "table",
            "tables",
            "workbook",
            "workbooks",
        }
        overview_terms = {
            "about",
            "available",
            "describe",
            "explain",
            "list",
            "overview",
            "show",
            "summarize",
            "summary",
        }
        return bool(tokens & metadata_terms and tokens & overview_terms)

    @classmethod
    def _looks_like_table_overview(
        cls, question: str, table_columns: dict[str, set[str]] | None
    ) -> bool:
        if not table_columns:
            return False
        text = cls._normalize_text(question)
        if not text or cls._looks_like_analytical_request(text):
            return False
        overview_prefixes = (
            "describe",
            "explain",
            "show me",
            "summarize",
            "tell me about",
            "what is in",
            "what is inside",
            "what does",
        )
        if not any(text.startswith(prefix) for prefix in overview_prefixes):
            return False
        question_tokens = set(text.split())
        for table_name, columns in table_columns.items():
            table_tokens = set(cls._normalize_text(table_name).split())
            column_tokens = {
                token
                for column in columns
                for token in cls._normalize_text(column).split()
                if len(token) > 2
            }
            if question_tokens & (table_tokens | column_tokens):
                return True
        return False

    @staticmethod
    def _is_affirmative_followup(question: str) -> bool:
        text = DataChatAgent._normalize_text(question)
        return text in {
            "yes",
            "yeah",
            "yep",
            "sure",
            "ok",
            "okay",
            "please",
            "please do",
            "do it",
            "go ahead",
            "continue",
            "that one",
            "the first one",
        }

    @staticmethod
    def _recent_context_requested_metadata(messages: list[dict[str, str]]) -> bool:
        metadata_terms = (
            "available data",
            "columns",
            "data coverage",
            "data sources",
            "high level summary",
            "sample data",
            "schema",
            "table names",
            "tables",
        )
        for message in reversed(messages[-8:]):
            if message.get("role") != "assistant":
                continue
            content = DataChatAgent._normalize_text(message.get("content", ""))
            if any(term in content for term in metadata_terms):
                return True
        return False

    @staticmethod
    def _looks_like_analytical_request(question: str) -> bool:
        text = DataChatAgent._normalize_text(question)
        analytical_patterns = (
            " average ",
            " avg ",
            " by ",
            " compare ",
            " correlation ",
            " forecast ",
            " group ",
            " highest ",
            " lowest ",
            " rank ",
            " sum ",
            " top ",
            " total ",
            " trend ",
            " where ",
        )
        padded = f" {text} "
        return any(pattern in padded for pattern in analytical_patterns)

    @staticmethod
    def _normalize_text(value: str) -> str:
        lowered = value.lower().strip()
        normalized = re.sub(r"[^a-z0-9]+", " ", lowered)
        return re.sub(r"\s+", " ", normalized).strip()

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
                    "sample_rows": table.sample_rows[:3],
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

    async def _build_numeric_extrema_response(self, state: AgentState) -> dict[str, Any]:
        schema = await self.catalog.get_schema(state.get("selected_data_sources"))
        specs = self._numeric_column_specs(schema, state.get("user_question", ""))
        if not specs:
            return {
                "answer": (
                    "I inspected the current catalog, but I could not find numeric measure "
                    "columns suitable for maximum-value profiling."
                ),
                "reasoning_summary": (
                    "Checked table metadata for numeric columns before deciding no safe "
                    "aggregate query was useful."
                ),
                "caveats": ["Identifier columns are excluded from generic max/min profiling."],
                "confidence": "medium",
                "artifacts": [],
                "sources": [],
            }

        add_event(
            state,
            "Generating query",
            "completed",
            "Built a deterministic aggregate query for numeric maxima.",
        )
        sql = self._numeric_extrema_sql(specs)
        state["sql_query"] = sql
        validation = self.sql_guard.validate(sql, state.get("table_columns", {}))
        state["sql_validation"] = {
            "is_valid": validation.is_valid,
            "errors": validation.errors,
            "warnings": validation.warnings,
            "used_tables": validation.used_tables,
            "used_columns": validation.used_columns,
        }
        if not validation.is_valid:
            state["errors"].extend(validation.errors)
            add_event(state, "Validating", "error", "Numeric aggregate SQL validation failed.")
            return {
                "answer": "I could not safely validate the numeric max/min query.",
                "reasoning_summary": (
                    "Generated a deterministic aggregate query but blocked execution."
                ),
                "caveats": validation.errors,
                "confidence": "low",
                "artifacts": [],
                "sources": [],
            }
        add_event(state, "Validating", "completed", "Numeric aggregate SQL validation passed.")

        add_event(state, "Executing", "running", "Computing numeric maxima across active tables.")
        result = await self.query_engine.execute_sql(sql, state.get("selected_data_sources"))
        rows = sorted(
            result.rows,
            key=lambda row: self._sortable_number(row.get("Maximum")),
            reverse=True,
        )
        state["sql_result"] = {
            "columns": result.columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": result.truncated,
            "duration_ms": result.duration_ms,
            "metadata": result.metadata,
        }
        add_event(
            state,
            "Executing",
            "completed",
            f"Computed maxima for {len(rows)} numeric field(s).",
            duration_ms=result.duration_ms,
        )

        critique_caveats = []
        if not rows:
            critique_caveats.append("No numeric aggregate rows were returned.")
        add_event(
            state,
            "Critiquing answer",
            "completed" if rows else "warning",
            "Checked that the numeric profile answers the max/min request.",
        )

        top_rows = rows[:5]
        answer_lines = [
            "I interpreted this as: find the maximum values across numeric business fields.",
            "",
        ]
        if top_rows:
            best = top_rows[0]
            best_label = self._max_row_phrase(best)
            answer_lines.append(
                "The largest maximum I found is "
                f"{self._format_number(best.get('Maximum'))} for {best.get('Field')} "
                f"in {best.get('Dataset')} / {best.get('Table')}{best_label}."
            )
            answer_lines.append("")
            answer_lines.append("Top maximum values:")
            for row in top_rows:
                answer_lines.append(
                    "- "
                    f"{row.get('Dataset')} / {row.get('Table')} / {row.get('Field')}: "
                    f"max {self._format_number(row.get('Maximum'))}"
                    f"{self._max_row_phrase(row)} "
                    f"(min {self._format_number(row.get('Minimum'))}, "
                    f"avg {self._format_number(row.get('Average'))})"
                )
        answer_lines.append(
            "\nThe table below includes the full numeric profile I computed. "
            "Identifier fields such as IDs are excluded so the result focuses on business measures."
        )

        chart_rows = top_rows[:8]
        artifacts: list[dict[str, Any]] = [
            {
                "type": "table",
                "title": "Numeric Maxima",
                "columns": result.columns,
                "rows": rows[: self.settings.sql_preview_row_limit],
                "truncated": len(rows) > self.settings.sql_preview_row_limit,
            }
        ]
        if chart_rows:
            artifacts.append(
                {
                    "type": "chart",
                    "title": "Top Numeric Maximum Values",
                    "spec": {
                        "data": [
                            {
                                "type": "bar",
                                "orientation": "h",
                                "x": [row.get("Maximum") for row in reversed(chart_rows)],
                                "y": [
                                    f"{row.get('Dataset')} / {row.get('Field')}"
                                    for row in reversed(chart_rows)
                                ],
                                "marker": {"color": "#0f766e"},
                                "hovertemplate": "%{y}<br>%{x:,}<extra></extra>",
                            }
                        ],
                        "layout": {
                            "margin": {"l": 160, "r": 24, "t": 24, "b": 48},
                            "xaxis": {"title": "Maximum value"},
                            "yaxis": {"title": ""},
                            "showlegend": False,
                        },
                    },
                }
            )

        return {
            "answer": "\n".join(answer_lines),
            "reasoning_summary": (
                "Inspected current metadata, generated a safe aggregate query, validated it, "
                "and computed maximum, minimum, and average values for numeric measure columns."
            ),
            "caveats": [
                "Generic max/min profiling excludes identifier-like columns such as *_id.",
                "If source files changed recently, rescan before relying on these values.",
                *critique_caveats,
            ],
            "confidence": "high",
            "artifacts": artifacts,
            "sources": [],
        }

    def _numeric_column_specs(self, schema: Any, question: str) -> list[dict[str, str]]:
        source_by_id = {source.id: source for source in schema.data_sources}
        specs: list[dict[str, str]] = []
        for table in schema.tables:
            source = source_by_id.get(table.data_source_id)
            dataset_name = self._friendly_name(source.name if source else table.data_source_id)
            for column in table.columns:
                if not self._is_numeric_data_type(column.data_type):
                    continue
                if self._is_ignored_numeric_column(column.normalized_name):
                    continue
                specs.append(
                    {
                        "dataset": dataset_name,
                        "table": table.original_name,
                        "canonical_table": table.canonical_name,
                        "column": column.normalized_name,
                        "field": column.original_name,
                        "label_column": self._label_column_for_table(table),
                    }
                )

        focus_tokens = self._analysis_focus_tokens(question)
        if not focus_tokens:
            return specs

        focused = [
            spec
            for spec in specs
            if focus_tokens
            & set(
                self._normalize_text(
                    f"{spec['dataset']} {spec['table']} {spec['field']} {spec['column']}"
                ).split()
            )
        ]
        return focused or specs

    @staticmethod
    def _numeric_extrema_sql(specs: list[dict[str, str]]) -> str:
        statements = []
        for spec in specs:
            column = DataChatAgent._quote_identifier(spec["column"])
            table = DataChatAgent._quote_identifier(spec["canonical_table"])
            label_column = spec.get("label_column")
            max_row_sql = (
                "CAST(NULL AS VARCHAR)"
                if not label_column
                else (
                    f"ARG_MAX(CAST({DataChatAgent._quote_identifier(label_column)} AS VARCHAR), "
                    f"CAST({column} AS DOUBLE))"
                )
            )
            statements.append(
                "SELECT "
                f"{DataChatAgent._quote_literal(spec['dataset'])} AS \"Dataset\", "
                f"{DataChatAgent._quote_literal(spec['table'])} AS \"Table\", "
                f"{DataChatAgent._quote_literal(spec['field'])} AS \"Field\", "
                f"{max_row_sql} AS \"Max row\", "
                f"COUNT({column}) AS \"Non-null rows\", "
                f"MIN(CAST({column} AS DOUBLE)) AS \"Minimum\", "
                f"MAX(CAST({column} AS DOUBLE)) AS \"Maximum\", "
                f"AVG(CAST({column} AS DOUBLE)) AS \"Average\" "
                f"FROM {table} WHERE {column} IS NOT NULL"
            )
        return "\nUNION ALL\n".join(statements)

    @staticmethod
    def _label_column_for_table(table: Any) -> str:
        preferred = (
            "metric",
            "project_name",
            "customer_name",
            "sku",
            "supplier",
            "vendor",
            "milestone_name",
            "material_family",
            "region",
            "product_family",
            "warehouse",
            "cost_category",
            "channel",
        )
        columns_by_name = {column.normalized_name: column for column in table.columns}
        for name in preferred:
            column = columns_by_name.get(name)
            if column and not DataChatAgent._is_numeric_data_type(column.data_type):
                return column.normalized_name
        for column in table.columns:
            if DataChatAgent._is_numeric_data_type(column.data_type):
                continue
            if DataChatAgent._is_identifier_like(column.normalized_name):
                continue
            return column.normalized_name
        return ""

    @staticmethod
    def _analysis_focus_tokens(question: str) -> set[str]:
        generic_tokens = {
            "a",
            "an",
            "are",
            "column",
            "columns",
            "do",
            "find",
            "for",
            "give",
            "highest",
            "is",
            "largest",
            "max",
            "maximum",
            "maximums",
            "me",
            "measure",
            "measures",
            "metric",
            "metrics",
            "min",
            "minimum",
            "minimums",
            "number",
            "numbers",
            "of",
            "show",
            "smallest",
            "the",
            "value",
            "values",
            "what",
            "which",
        }
        return set(DataChatAgent._normalize_text(question).split()) - generic_tokens

    @staticmethod
    def _is_numeric_data_type(data_type: str) -> bool:
        lowered = data_type.lower()
        if any(blocked in lowered for blocked in ("bool", "date", "time")):
            return False
        return any(
            term in lowered
            for term in ("int", "float", "double", "decimal", "numeric", "number", "real")
        )

    @staticmethod
    def _is_ignored_numeric_column(column_name: str) -> bool:
        if column_name == "formula":
            return True
        return DataChatAgent._is_identifier_like(column_name)

    @staticmethod
    def _is_identifier_like(column_name: str) -> bool:
        normalized = DataChatAgent._normalize_text(column_name)
        return (
            normalized == "id"
            or normalized.endswith(" id")
            or normalized in {"row number", "index"}
        )

    @staticmethod
    def _quote_identifier(value: str) -> str:
        return f'"{value.replace(chr(34), chr(34) + chr(34))}"'

    @staticmethod
    def _quote_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    @staticmethod
    def _sortable_number(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("-inf")

    @staticmethod
    def _format_number(value: Any) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "n/a"
        if number.is_integer():
            return f"{number:,.0f}"
        if abs(number) >= 100:
            return f"{number:,.2f}"
        return f"{number:.4g}"

    @staticmethod
    def _max_row_phrase(row: dict[str, Any]) -> str:
        label = row.get("Max row")
        if label in (None, ""):
            return ""
        return f" ({label})"

    async def _build_metadata_response(self, state: AgentState) -> dict[str, Any]:
        schema = await self.catalog.get_schema(state.get("selected_data_sources"))
        source_by_id = {source.id: source for source in schema.data_sources}
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

        relationship_lines = self._metadata_relationship_lines(
            schema.relationships,
            {table.canonical_name: table.original_name for table in tables},
        )
        row_phrase = (
            f", covering about {total_rows:,} scanned rows"
            if known_row_counts and len(known_row_counts) == table_count
            else ""
        )
        source_label = "data source" if source_count == 1 else "data sources"
        table_label = "table or sheet" if table_count == 1 else "tables or sheets"
        answer_parts = [
            "Here is the current data landscape.",
            "",
            f"I see {source_count} configured {source_label} with {table_count} "
            f"queryable {table_label}{row_phrase}. The data currently covers:",
            *self._metadata_business_summary_lines(schema.data_sources, tables),
        ]
        if relationship_lines:
            answer_parts.extend(
                [
                    "",
                    "Useful relationship paths are already visible:",
                    *relationship_lines,
                ]
            )
        answer_parts.append(
            "\nI put the detailed catalog in the table below. Good next questions would be "
            "'which SKUs are below reorder point?', 'compare revenue to targets by region', "
            "or 'which projects are overspending?'."
        )

        artifact_rows = []
        dataset_row_counts: dict[str, int] = {}
        for table in tables:
            source = source_by_id.get(table.data_source_id)
            dataset_name = self._friendly_name(source.name if source else table.data_source_id)
            columns = [column.normalized_name for column in table.columns]
            if table.row_count is not None:
                dataset_row_counts[dataset_name] = (
                    dataset_row_counts.get(dataset_name, 0) + table.row_count
                )
            artifact_rows.append(
                {
                    "Dataset": dataset_name,
                    "Table / sheet": table.original_name,
                    "Rows": table.row_count,
                    "What it contains": self._metadata_table_description(table),
                    "Key fields": ", ".join(columns[:8]),
                    "Sample row": self._compact_sample_row(table.sample_rows),
                }
            )

        preview_limit = self.settings.sql_preview_row_limit
        caveats = []
        if len(known_row_counts) != table_count:
            caveats.append("Some tables do not have row counts in the current metadata scan.")
        if any(source.status != "active" for source in schema.data_sources):
            caveats.append("One or more configured data sources are not active.")
        caveats.append("If files changed since the last scan, rescan before relying on row counts.")

        artifacts: list[dict[str, Any]] = [
            {
                "type": "table",
                "title": "Data Catalog",
                "columns": [
                    "Dataset",
                    "Table / sheet",
                    "Rows",
                    "What it contains",
                    "Key fields",
                    "Sample row",
                ],
                "rows": artifact_rows[:preview_limit],
                "truncated": len(artifact_rows) > preview_limit,
            }
        ]
        if dataset_row_counts:
            artifacts.append(
                {
                    "type": "chart",
                    "title": "Rows by Dataset",
                    "spec": {
                        "data": [
                            {
                                "type": "bar",
                                "x": list(dataset_row_counts.keys()),
                                "y": list(dataset_row_counts.values()),
                                "marker": {"color": "#0f766e"},
                                "hovertemplate": "%{x}<br>%{y:,} rows<extra></extra>",
                            }
                        ],
                        "layout": {
                            "margin": {"l": 52, "r": 24, "t": 24, "b": 72},
                            "xaxis": {"title": "Dataset"},
                            "yaxis": {"title": "Rows"},
                            "showlegend": False,
                        },
                    },
                }
            )

        return {
            "answer": "\n".join(answer_parts),
            "reasoning_summary": (
                "Read the current metadata catalog and summarized the available sources, "
                "tables, columns, samples, and relationships. No generated SQL or Python "
                "was executed for this overview."
            ),
            "caveats": caveats,
            "confidence": "high",
            "artifacts": artifacts,
            "sources": [],
        }

    @staticmethod
    def _metadata_business_summary_lines(data_sources: list[Any], tables: list[Any]) -> list[str]:
        lines: list[str] = []
        for source in data_sources:
            source_tables = [table for table in tables if table.data_source_id == source.id]
            if not source_tables:
                lines.append(
                    f"- {DataChatAgent._friendly_name(source.name)}: no scanned tables yet."
                )
                continue
            descriptions = [
                DataChatAgent._metadata_table_description(table) for table in source_tables
            ]
            summary = DataChatAgent._combine_descriptions(descriptions)
            table_names = ", ".join(table.original_name for table in source_tables[:5])
            if len(source_tables) > 5:
                table_names += f", plus {len(source_tables) - 5} more"
            lines.append(
                f"- {DataChatAgent._friendly_name(source.name)}: {summary} "
                f"Tables/sheets: {table_names}."
            )
        return lines

    @staticmethod
    def _metadata_relationship_lines(
        relationships: list[Any], table_display_names: dict[str, str]
    ) -> list[str]:
        lines = []
        for relationship in relationships[:6]:
            left_table = table_display_names.get(relationship.left_table, relationship.left_table)
            right_table = table_display_names.get(
                relationship.right_table, relationship.right_table
            )
            lines.append(
                "- "
                f"{left_table} links to {right_table} through "
                f"{relationship.left_column} and {relationship.right_column} "
                f"({relationship.confidence:.0%} confidence)."
            )
        if len(relationships) > 6:
            lines.append(f"- {len(relationships) - 6} more inferred relationship(s)")
        return lines

    @staticmethod
    def _metadata_table_description(table: Any) -> str:
        column_text = " ".join(column.normalized_name for column in table.columns).lower()
        name_text = table.original_name.lower()
        combined = f"{name_text} {column_text}"
        tokens = set(DataChatAgent._normalize_text(combined).split())
        if tokens & {"quality", "inspection", "inspections", "defect", "defects"}:
            return "Quality inspection outcomes, sample sizes, and defect rates."
        if tokens & {"supplier", "suppliers", "lead", "contract"}:
            return "Supplier coverage, countries, lead times, and contract status."
        if tokens & {"milestone", "milestones", "planned", "actual"}:
            return "Milestone schedules, completion dates, and delivery status."
        if tokens & {"spend", "transaction", "transactions", "vendor", "amount"}:
            return "Spend transactions, vendors, cost categories, dates, and amounts."
        if tokens & {"project", "projects", "budget", "sponsor"}:
            return "Project master data, budgets, sponsors, regions, and business units."
        if tokens & {"target", "targets", "monthly", "month"}:
            return "Monthly targets by period and business dimension."
        if tokens & {"order", "orders", "revenue", "margin", "channel"}:
            return "Orders, revenue, margins, product families, status, and channels."
        if tokens & {"customer", "customers", "segment", "owner"}:
            return "Customer master data, regions, segments, and account ownership."
        if tokens & {"inventory", "warehouse", "reorder"}:
            return "Inventory quantities, value, warehouses, and reorder signals."
        if "summary" in combined or "metric" in combined:
            return "Precalculated summary metrics from the source workbook."
        return "Structured business records available for querying and analysis."

    @staticmethod
    def _combine_descriptions(descriptions: list[str]) -> str:
        unique = []
        for description in descriptions:
            short = description.rstrip(".")
            if short not in unique:
                unique.append(short)
        if not unique:
            return "Structured business records."
        if len(unique) == 1:
            return f"{unique[0]}."
        return "; ".join(unique[:4]) + "."

    @staticmethod
    def _friendly_name(value: str) -> str:
        cleaned = value.removeprefix("example_").replace("_", " ").strip()
        return cleaned.title() if cleaned else value

    @staticmethod
    def _compact_sample_row(sample_rows: list[dict[str, Any]]) -> str:
        if not sample_rows:
            return ""
        row = sample_rows[0]
        parts = []
        for key, value in list(row.items())[:5]:
            parts.append(f"{key}={DataChatAgent._compact_value(value)}")
        if len(row) > 5:
            parts.append("...")
        return "; ".join(parts)

    @staticmethod
    def _compact_value(value: Any) -> str:
        if value is None:
            return "null"
        rendered = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
        return rendered if len(rendered) <= 80 else f"{rendered[:77]}..."

    def _build_artifacts(self, state: AgentState) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        if state.get("sql_result", {}).get("rows"):
            artifacts.append(
                {
                    "type": "table",
                    "title": "SQL result",
                    "columns": state["sql_result"].get("columns", []),
                    "rows": state["sql_result"].get("rows", [])[
                        : self.settings.sql_preview_row_limit
                    ],
                    "truncated": state["sql_result"].get("truncated", False),
                }
            )
        python_result = state.get("python_result", {})
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
        validation = state.get("sql_validation", {})
        used_tables = validation.get("used_tables") or []
        used_columns = validation.get("used_columns") or {}
        return [{"table": table, "columns": used_columns.get(table, [])} for table in used_tables]

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
                "confidence": state.get("critique", {}).get("confidence", "medium"),
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
                        "errors": state.get("errors", [])[-5:],
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
                "confidence": final.get("confidence")
                or state.get("critique", {}).get("confidence", "medium"),
            }
        except Exception as exc:
            caveats = state.get("critique", {}).get("caveats", [])
            caveats.append(f"Final model summary was unavailable: {exc}")
            return {
                "answer": self._fallback_answer(state),
                "reasoning_summary": "Used validated execution results and a fallback summarizer.",
                "caveats": caveats,
                "confidence": state.get("critique", {}).get("confidence", "medium"),
            }

    @staticmethod
    def _fallback_answer(state: AgentState) -> str:
        if state.get("sql_result", {}).get("rows"):
            row_count = state["sql_result"].get("row_count", 0)
            return f"I found {row_count} result row(s). See the result table for details."
        if state.get("python_result", {}).get("stdout"):
            return state["python_result"]["stdout"].strip()
        if state.get("errors"):
            return (
                "I could not complete the analysis safely. "
                "See caveats for the validation or execution errors."
            )
        return "The analysis completed, but no rows were returned."
