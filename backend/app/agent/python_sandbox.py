from __future__ import annotations

import asyncio
import json
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.datasources.query_engine import QueryEngine


@dataclass
class PythonExecutionResult:
    ok: bool
    answer: str = ""
    stdout: str = ""
    result_table: list[dict[str, Any]] = field(default_factory=list)
    chart: dict[str, Any] | None = None
    error: str | None = None


class PythonSandbox:
    def __init__(self, query_engine: QueryEngine, settings: Settings | None = None):
        self.query_engine = query_engine
        self.settings = settings or get_settings()

    async def execute(
        self,
        code: str,
        selected_source_ids: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> PythonExecutionResult:
        run_dir = self.settings.python_work_dir / str(uuid.uuid4())
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            tables = await self.query_engine.materialize_for_python(run_dir, selected_source_ids)
            payload = {"code": code, "tables": tables, "context": context or {}}
            worker = Path(__file__).with_name("sandbox_worker.py")
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(worker),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(json.dumps(payload).encode("utf-8")),
                    timeout=self.settings.python_timeout_seconds,
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                return PythonExecutionResult(ok=False, error="Python analysis timed out.")

            if process.returncode != 0:
                return PythonExecutionResult(
                    ok=False,
                    error=(stderr.decode("utf-8", errors="replace") or "Sandbox failed."),
                )

            try:
                data = json.loads(stdout.decode("utf-8"))
            except json.JSONDecodeError as exc:
                return PythonExecutionResult(ok=False, error=f"Invalid sandbox output: {exc}")

            return PythonExecutionResult(
                ok=bool(data.get("ok")),
                answer=data.get("answer") or "",
                stdout=data.get("stdout") or "",
                result_table=data.get("result_table") or [],
                chart=data.get("chart"),
                error=data.get("error"),
            )
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)
