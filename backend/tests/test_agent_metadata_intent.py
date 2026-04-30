from app.agent.graph import DataChatAgent


def test_broad_data_questions_are_metadata_lookup() -> None:
    assert DataChatAgent._looks_like_metadata_lookup("tell me about the data")
    assert DataChatAgent._looks_like_metadata_lookup("what is the data in the tables")
    assert DataChatAgent._looks_like_metadata_lookup("show tables and columns")
    assert DataChatAgent._looks_like_metadata_lookup("what am I looking at?")
    assert DataChatAgent._looks_like_metadata_lookup("walk me through this")


def test_question_suggestion_requests_are_separate_from_metadata_overview() -> None:
    assert DataChatAgent._is_question_suggestion_request("What questions can I ask?")
    assert DataChatAgent._is_question_suggestion_request(
        "what kind of questions I can ask about the data"
    )
    assert DataChatAgent._is_question_suggestion_request(
        "what questions I can ask about these files"
    )
    assert DataChatAgent._is_question_suggestion_request("Give me example prompts")
    assert not DataChatAgent._looks_like_metadata_lookup("What can I ask about?")


def test_affirmative_followup_resolves_to_metadata_when_context_offered_summary() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "Are you looking for a high-level summary of all tables and columns?",
        },
        {"role": "user", "content": "yes"},
    ]

    assert DataChatAgent._is_affirmative_followup("yes")
    assert DataChatAgent._recent_context_requested_metadata(messages)


def test_analytical_questions_are_not_forced_to_metadata() -> None:
    assert not DataChatAgent._looks_like_metadata_lookup("top 5 customers by revenue")
    assert DataChatAgent._looks_like_analytical_request("top 5 customers by revenue")


def test_known_table_overview_is_metadata_without_capturing_analytics() -> None:
    table_columns = {"sales_orders": {"order_id", "customer_id", "revenue"}}

    assert DataChatAgent._looks_like_table_overview("describe orders", table_columns)
    assert not DataChatAgent._looks_like_table_overview(
        "show revenue by customer", table_columns
    )


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


def test_route_after_plan_keeps_standard_tabular_requests_on_sql() -> None:
    agent = DataChatAgent.__new__(DataChatAgent)
    state = {
        "user_question": "provide more details and order by highest value",
        "question_type": "requires_python",
        "execution_plan": {"tool": "python"},
    }

    assert agent.route_after_plan(state) == "sql"
    assert state["execution_plan"]["tool"] == "sql"
