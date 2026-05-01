from __future__ import annotations

import re
from typing import Any

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")

_KNOWN_REPLACEMENTS = {
    "绘图": " chart ",
    "图表": " chart ",
    "数据": " data ",
    "查询": " query ",
    "表格": " table ",
}


def sanitize_user_text(value: Any) -> str:
    """Clean generated assistant prose without touching raw data artifacts."""
    text = "" if value is None else str(value)
    if not text:
        return ""

    text = text.replace("\ufffd", "")
    for source, replacement in _KNOWN_REPLACEMENTS.items():
        text = text.replace(source, replacement)

    text = _CJK_RE.sub("", text)
    text = _MULTISPACE_RE.sub(" ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([(\[{])\s+", r"\1", text)
    text = re.sub(r"\s+([)\]}])", r"\1", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sanitize_user_text_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [cleaned for item in values if (cleaned := sanitize_user_text(item))]


def sanitize_status_events(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        return []

    cleaned_events: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        cleaned = {
            key: sanitize_user_text(value) if isinstance(value, str) else value
            for key, value in event.items()
        }
        cleaned_events.append(cleaned)
    return cleaned_events
