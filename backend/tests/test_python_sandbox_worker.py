from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_sandbox_worker_can_create_chart_from_cached_sql_result():
    worker = Path(__file__).parents[1] / "app" / "agent" / "sandbox_worker.py"
    code = """
import json
import plotly.express as px

df = sql_result_df.rename(columns={"func_area_txt": "function"})
chart = px.bar(
    df,
    x="function",
    y="cc_po_volume",
    title=json.loads('{"text": "PO volume by function"}')["text"],
)
result_table = df
answer = "Created a chart from the grouped result."
"""
    payload = {
        "code": code,
        "tables": [],
        "context": {
            "sql_result": {
                "rows": [
                    {"func_area_txt": "Information Technology", "cc_po_volume": 828},
                    {"func_area_txt": "Manufacturing Support", "cc_po_volume": 776},
                ]
            }
        },
    }

    result = subprocess.run(
        [sys.executable, str(worker)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        check=True,
    )
    data = json.loads(result.stdout.decode("utf-8"))

    assert data["ok"] is True
    assert data["answer"] == "Created a chart from the grouped result."
    assert data["result_table"][0]["function"] == "Information Technology"
    assert data["chart"]["data"][0]["type"] == "bar"
    assert data["chart"]["data"][0]["x"] == [
        "Information Technology",
        "Manufacturing Support",
    ]
