from app.agent.graph import DataChatAgent


def test_fallback_answer_summarizes_grouped_sql_results():
    answer = DataChatAgent._fallback_answer(
        {
            "sql_result": {
                "columns": ["source_table", "plant", "cost_center", "record_count", "pct_of_table"],
                "rows": [
                    {
                        "source_table": "po_with_cost_center",
                        "plant": "1000",
                        "cost_center": 1012843,
                        "record_count": 42,
                        "pct_of_table": 12.5,
                    }
                ],
                "row_count": 1,
            }
        }
    )

    assert "grouped result row(s)" in answer
    assert "record_count" in answer
    assert "plant=1000" in answer


def test_fallback_answer_includes_detail_columns_when_no_aggregate_metric_exists():
    answer = DataChatAgent._fallback_answer(
        {
            "sql_result": {
                "columns": ["po_number", "plant"],
                "rows": [{"po_number": 4801242967, "plant": "1000"}],
                "row_count": 1,
            }
        }
    )

    assert "columns po_number, plant" in answer
    assert "po_number=4801242967" in answer


def test_bounded_confidence_never_exceeds_failed_critique():
    assert (
        DataChatAgent._bounded_confidence("high", {"passes": False, "confidence": "high"})
        == "low"
    )


def test_bounded_confidence_never_exceeds_critique_confidence():
    assert (
        DataChatAgent._bounded_confidence("high", {"passes": True, "confidence": "medium"})
        == "medium"
    )
