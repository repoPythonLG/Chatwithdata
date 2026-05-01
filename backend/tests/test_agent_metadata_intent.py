from app.agent.graph import DataChatAgent


def test_sql_validation_repairs_twice_then_falls_back_to_python() -> None:
    agent = DataChatAgent.__new__(DataChatAgent)

    state = {"sql_validation": {"is_valid": False}, "sql_attempts": 1}
    assert agent.route_after_sql_validation(state) == "repair"

    state = {"sql_validation": {"is_valid": False}, "sql_attempts": 2}
    assert agent.route_after_sql_validation(state) == "repair"

    assert (
        agent.route_after_sql_validation(
            {"sql_validation": {"is_valid": False}, "sql_attempts": 3, "python_attempts": 0}
        )
        == "python"
    )


def test_sql_execution_falls_back_to_python_after_three_failures() -> None:
    agent = DataChatAgent.__new__(DataChatAgent)

    assert agent.route_after_sql_execution({"sql_attempts": 1}) == "repair"
    assert agent.route_after_sql_execution({"sql_attempts": 2}) == "repair"
    assert agent.route_after_sql_execution({"sql_attempts": 3, "python_attempts": 0}) == "python"


def test_critique_routes_to_sql_repair_then_python_when_sql_is_exhausted() -> None:
    agent = DataChatAgent.__new__(DataChatAgent)

    assert (
        agent.route_after_critique(
            {
                "critique": {"passes": False, "needs_repair": True, "repair_tool": "sql"},
                "critique_attempts": 1,
                "sql_attempts": 1,
            }
        )
        == "sql"
    )
    assert (
        agent.route_after_critique(
            {
                "critique": {"passes": False, "needs_repair": True, "repair_tool": "sql"},
                "critique_attempts": 1,
                "sql_attempts": 3,
                "python_attempts": 0,
            }
        )
        == "python"
    )


def test_route_after_plan_respects_llm_tool_choice() -> None:
    agent = DataChatAgent.__new__(DataChatAgent)
    state = {
        "user_question": "provide more details and order by highest value",
        "question_type": "requires_python",
        "execution_plan": {"tool": "python"},
    }

    assert agent.route_after_plan(state) == "python"
    assert state["execution_plan"]["tool"] == "python"


def test_route_after_plan_uses_planned_sql_even_when_classifier_preferred_chart() -> None:
    agent = DataChatAgent.__new__(DataChatAgent)
    state = {
        "user_question": "show it in table",
        "question_type": "requires_chart",
        "execution_plan": {"tool": "sql"},
    }

    assert agent.route_after_plan(state) == "sql"


def test_generated_logic_is_exposed_for_advanced_ui_even_after_fallback() -> None:
    state = {
        "sql_query": "SELECT amount FROM spend ORDER BY amount DESC LIMIT 10",
        "python_code": "result = query('SELECT AVG(amount) AS mean_amount FROM spend')",
        "python_result": {"ok": True},
    }

    assert DataChatAgent._exposed_sql_query(state) == state["sql_query"]
    assert DataChatAgent._exposed_python_code(state) == state["python_code"]


def test_blank_generated_logic_is_not_exposed() -> None:
    assert DataChatAgent._exposed_sql_query({"sql_query": "   "}) is None
    assert DataChatAgent._exposed_python_code({"python_code": ""}) is None


def test_llm_schema_interpretation_can_resolve_ambiguous_to_sql() -> None:
    state = {"question_type": "ambiguous", "classification": {"question_type": "ambiguous"}}
    DataChatAgent._apply_schema_interpretation(
        state,
        {
            "question_type": "sql_answerable",
            "resolved_question": "List the distinct warehouse values.",
            "selected_tables": ["example_inventory_quality__inventory"],
            "selected_columns": ["warehouse"],
            "clarification_question": None,
            "reasoning_summary": "The LLM resolved the typo-heavy wording using schema context.",
        },
    )

    assert state["question_type"] == "sql_answerable"
    assert state["classification"]["question_type"] == "sql_answerable"
    assert state["schema_interpretation"] == {
        "question_type": "sql_answerable",
        "resolved_question": "List the distinct warehouse values.",
        "selected_tables": ["example_inventory_quality__inventory"],
        "selected_columns": ["warehouse"],
        "clarification_question": None,
        "reasoning_summary": "The LLM resolved the typo-heavy wording using schema context.",
    }


def test_invalid_llm_schema_interpretation_stays_ambiguous() -> None:
    state = {"question_type": "ambiguous", "classification": {"question_type": "ambiguous"}}
    DataChatAgent._apply_schema_interpretation(
        state,
        {
            "question_type": "not_a_valid_type",
            "resolved_question": None,
            "clarification_question": "Which field should I use?",
        },
    )

    assert state["question_type"] == "ambiguous"
    assert state["classification"]["clarification_question"] == "Which field should I use?"


def test_react_action_application_maps_sql_and_counts_attempt() -> None:
    agent = DataChatAgent.__new__(DataChatAgent)
    state = {"sql_attempts": 0}
    action = DataChatAgent._normalize_react_action(
        {
            "thought_summary": "Use SQL for a grouped count.",
            "phase": "Generate query",
            "action": "sql_query",
            "action_input": {"sql": 'SELECT COUNT(*) AS row_count FROM "orders"'},
            "expected_output": "row_count",
        }
    )

    agent._apply_react_action_to_state(state, action, increment_attempt=True)

    assert state["sql_attempts"] == 1
    assert state["sql_query"] == 'SELECT COUNT(*) AS row_count FROM "orders"'
    assert state["execution_plan"]["tool"] == "sql"
    assert state["current_action"]["action"] == "sql_query"


def test_react_review_route_retries_when_review_rejects_action() -> None:
    agent = DataChatAgent.__new__(DataChatAgent)
    state = {
        "react_rounds": 1,
        "sql_attempts": 0,
        "python_attempts": 0,
        "action_review": {"approved": False, "issues": ["Wrong tool"]},
        "status_events": [],
    }

    assert agent.route_after_action_review(state) == "retry"
    assert state["status_events"][-1]["step"] == "Retrying"


def test_react_verification_maps_sql_repair_to_sql_action() -> None:
    agent = DataChatAgent.__new__(DataChatAgent)

    verification = agent._verification_from_critique(
        {
            "passes": False,
            "confidence": "low",
            "summary": "SQL missed a requested metric.",
            "caveats": ["Missing metric"],
            "needs_repair": True,
            "repair_tool": "sql",
        }
    )

    assert verification == {
        "passes": False,
        "confidence": "low",
        "summary": "SQL missed a requested metric.",
        "caveats": ["Missing metric"],
        "needs_repair": True,
        "repair_action": "sql_query",
    }
