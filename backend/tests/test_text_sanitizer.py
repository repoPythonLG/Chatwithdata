from app.agent.text_sanitizer import sanitize_status_events, sanitize_user_text


def test_sanitize_user_text_removes_replacement_character_and_cjk_fragments():
    text = "The result is�rica-centric and limited to full绘图 output."

    assert sanitize_user_text(text) == "The result isrica-centric and limited to full chart output."


def test_sanitize_user_text_preserves_markdown_formatting():
    assert sanitize_user_text("**Row counts**: 10 rows.") == "**Row counts**: 10 rows."


def test_sanitize_status_events_cleans_llm_generated_details():
    events = [{"step": "Critiquing answer", "status": "completed", "detail": "Needs 绘图 check �"}]

    assert sanitize_status_events(events) == [
        {"step": "Critiquing answer", "status": "completed", "detail": "Needs chart check"}
    ]
