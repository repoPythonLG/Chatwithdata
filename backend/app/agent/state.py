from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    conversation_id: str
    user_question: str
    messages: list[dict[str, str]]
    selected_data_sources: list[str] | None
    schema_context: str
    table_columns: dict[str, set[str]]
    schema_interpretation: dict[str, Any]
    question_type: str
    classification: dict[str, Any]
    execution_plan: dict[str, Any]
    sql_query: str
    sql_validation: dict[str, Any]
    sql_result: dict[str, Any]
    python_code: str
    python_validation: dict[str, Any]
    python_result: dict[str, Any]
    critique: dict[str, Any]
    final_response: dict[str, Any]
    current_action: dict[str, Any]
    action_review: dict[str, Any]
    action_result: dict[str, Any]
    verification: dict[str, Any]
    draft_final_response: dict[str, Any]
    react_feedback: dict[str, Any]
    react_history: list[dict[str, Any]]
    react_rounds: int
    errors: list[str]
    artifacts: list[dict[str, Any]]
    status_events: list[dict[str, Any]]
    sql_attempts: int
    python_attempts: int
    critique_attempts: int
