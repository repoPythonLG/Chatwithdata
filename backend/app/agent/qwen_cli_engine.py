from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.db.models import ContractDocument, DataSource, TableMetadata

ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
CONTRACT_DB_ROLE = "contract_database"


@dataclass
class QwenCliResult:
    ok: bool
    answer: str
    raw_output: str
    workspace: str
    command: list[str] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    exit_code: int | None = None
    duration_ms: int = 0
    error: str | None = None


@dataclass
class QwenCliEvent:
    kind: str
    message: str = ""
    content: str = ""
    result: QwenCliResult | None = None


class QwenCliEngine:
    """Run the configured CLI engine against copied data files in an isolated workspace."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
        user_id: str | None = None,
    ):
        self.session = session
        self.settings = settings or get_settings()
        self.user_id = user_id

    async def stream(
        self,
        *,
        question: str,
        messages: list[dict[str, str]],
        selected_data_sources: list[str] | None,
    ) -> AsyncIterator[QwenCliEvent]:
        started = time.perf_counter()
        workspace = self.settings.qwen_work_dir / str(uuid.uuid4())
        data_dir = workspace / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        yield QwenCliEvent(kind="status", message="Preparing data-only engine workspace.")

        sources = await self._load_sources(selected_data_sources)
        copied_files = self._copy_sources(sources, data_dir)
        documents = await self._load_contract_documents()
        copied_documents = self._copy_contract_documents(documents, data_dir)
        approved_files = [*copied_files, *copied_documents]
        manifest = self._write_manifest(data_dir, copied_files, copied_documents, sources)
        prompt = self._build_prompt(question, messages, approved_files, manifest)
        prompt_path = data_dir / "PROMPT.md"
        prompt_path.write_text(prompt, encoding="utf-8")

        command = self._build_command(prompt)
        yield QwenCliEvent(
            kind="status",
            message="Starting Intelligence Engine in the data-only workspace.",
        )

        output_parts: list[str] = []
        output_chars = 0
        truncated = False
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=data_dir,
                env=self._process_env(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
            )
        except OSError as exc:
            result = QwenCliResult(
                ok=False,
                answer=f"Intelligence Engine could not be started: {exc}",
                raw_output="",
                workspace=str(data_dir),
                command=[],
                files=approved_files,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error=str(exc),
            )
            yield QwenCliEvent(kind="final", result=result)
            return

        try:
            assert process.stdout is not None
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self.settings.qwen_timeout_seconds
            while True:
                remaining_seconds = deadline - loop.time()
                if remaining_seconds <= 0:
                    raise asyncio.TimeoutError
                chunk = await asyncio.wait_for(
                    process.stdout.readline(),
                    timeout=remaining_seconds,
                )
                if not chunk:
                    break
                text = self._clean_output(chunk.decode("utf-8", errors="replace"))
                if not text:
                    continue
                if output_chars < self.settings.qwen_max_output_chars:
                    remaining_chars = self.settings.qwen_max_output_chars - output_chars
                    stored = text[:remaining_chars]
                    output_parts.append(stored)
                    output_chars += len(stored)
                    if len(text) > remaining_chars:
                        truncated = True
                else:
                    truncated = True
                yield QwenCliEvent(kind="output", content=text)
            remaining_seconds = deadline - loop.time()
            if remaining_seconds <= 0:
                raise asyncio.TimeoutError
            exit_code = await asyncio.wait_for(process.wait(), timeout=remaining_seconds)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raw_output = "".join(output_parts)
            result = QwenCliResult(
                ok=False,
                answer="Intelligence Engine timed out before it could finish the analysis.",
                raw_output=raw_output,
                workspace=str(data_dir),
                command=[],
                files=approved_files,
                exit_code=process.returncode,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error="Intelligence Engine timed out.",
            )
            yield QwenCliEvent(kind="final", result=result)
            return

        raw_output = "".join(output_parts).strip()
        if truncated:
            raw_output = (
                f"{raw_output}\n\n[Output truncated at "
                f"{self.settings.qwen_max_output_chars} characters.]"
            )
        answer = (
            self._extract_answer(raw_output)
            or "Intelligence Engine completed without returning visible output."
        )
        ok = exit_code == 0
        if not ok and not raw_output:
            answer = f"Intelligence Engine failed with exit code {exit_code}."

        result = QwenCliResult(
            ok=ok,
            answer=answer,
            raw_output=raw_output,
            workspace=str(data_dir),
            command=[],
            files=approved_files,
            exit_code=exit_code,
            duration_ms=int((time.perf_counter() - started) * 1000),
            error=None if ok else f"Intelligence Engine exited with code {exit_code}.",
        )
        yield QwenCliEvent(kind="final", result=result)

    async def run(
        self,
        *,
        question: str,
        messages: list[dict[str, str]],
        selected_data_sources: list[str] | None,
    ) -> QwenCliResult:
        final: QwenCliResult | None = None
        async for event in self.stream(
            question=question,
            messages=messages,
            selected_data_sources=selected_data_sources,
        ):
            if event.result is not None:
                final = event.result
        if final is None:
            return QwenCliResult(
                ok=False,
                answer="Intelligence Engine did not produce a result.",
                raw_output="",
                workspace="",
                error="No final Intelligence Engine result.",
            )
        return final

    async def _load_sources(self, selected_data_sources: list[str] | None) -> list[DataSource]:
        statement = (
            select(DataSource)
            .options(selectinload(DataSource.tables).selectinload(TableMetadata.columns))
            .where(DataSource.status == "active")
            .order_by(DataSource.name)
        )
        result = await self.session.execute(statement)
        sources = list(result.scalars().unique().all())
        if selected_data_sources:
            selected = set(selected_data_sources)
            return [source for source in sources if source.id in selected]
        contract_sources = [
            source for source in sources if (source.profile or {}).get("role") == CONTRACT_DB_ROLE
        ]
        return contract_sources

    async def _load_contract_documents(self) -> list[ContractDocument]:
        statement = select(ContractDocument).order_by(ContractDocument.created_at)
        if self.user_id:
            statement = statement.where(ContractDocument.user_id == self.user_id)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    def _copy_sources(
        self, sources: list[DataSource], data_dir: Path
    ) -> list[dict[str, Any]]:
        copied: list[dict[str, Any]] = []
        for index, source in enumerate(sources, start=1):
            source_path = Path(source.path)
            suffix = source_path.suffix
            safe_name = self._safe_filename(source.name or source_path.stem)
            target = data_dir / f"{index:02d}_{safe_name}{suffix}"
            if source_path.exists():
                shutil.copy2(source_path, target)
                status = "copied"
                error = None
            else:
                status = "missing"
                error = f"Source path does not exist: {source.path}"
            copied.append(
                {
                    "id": source.id,
                    "name": source.name,
                    "source_type": source.source_type,
                    "original_path": source.path,
                    "workspace_path": str(target.relative_to(data_dir)),
                    "status": status,
                    "error": error,
                    "tables": [
                        {
                            "name": table.original_name,
                            "canonical_name": table.canonical_name,
                            "row_count": table.row_count,
                            "columns": [column.normalized_name for column in table.columns],
                        }
                        for table in source.tables
                    ],
                }
            )
        return copied

    def _copy_contract_documents(
        self, documents: list[ContractDocument], data_dir: Path
    ) -> list[dict[str, Any]]:
        copied: list[dict[str, Any]] = []
        document_dir = data_dir / "contract_documents"
        document_dir.mkdir(exist_ok=True)
        for index, document in enumerate(documents, start=1):
            source_path = Path(document.path)
            safe_name = self._safe_filename(document.filename or document.name)
            target = document_dir / f"{index:02d}_{safe_name}"
            status = "copied"
            error = None
            if source_path.exists():
                shutil.copy2(source_path, target)
            else:
                status = "missing"
                error = f"Contract document path does not exist: {document.path}"

            text_workspace_path = None
            if document.extracted_text_path:
                extracted_path = Path(document.extracted_text_path)
                if extracted_path.exists():
                    text_target = document_dir / f"{index:02d}_{safe_name}.extracted.txt"
                    shutil.copy2(extracted_path, text_target)
                    text_workspace_path = str(text_target.relative_to(data_dir))

            copied.append(
                {
                    "id": document.id,
                    "name": document.name,
                    "source_type": "contract_document",
                    "original_path": document.path,
                    "workspace_path": str(target.relative_to(data_dir)),
                    "extracted_text_workspace_path": text_workspace_path,
                    "status": status,
                    "error": error,
                    "tables": [],
                }
            )
        return copied

    def _write_manifest(
        self,
        data_dir: Path,
        copied_files: list[dict[str, Any]],
        copied_documents: list[dict[str, Any]],
        sources: list[DataSource],
    ) -> Path:
        lines = [
            "# Contract Analysis Workspace",
            "",
            "This folder contains the only approved files for this analysis run.",
            "Only answer questions about the contract database and uploaded contract documents.",
            "Do not inspect parent folders, home folders, system folders, network locations, or",
            "any path outside this current working directory.",
            "Write scratch outputs only under `scratch/`.",
            "",
            "## Contract database",
            "",
        ]
        for item in copied_files:
            lines.append(f"- `{item['workspace_path']}` ({item['source_type']}): {item['name']}")
            if item["status"] != "copied":
                lines.append(f"  - Warning: {item['error']}")
            for table in item["tables"][:12]:
                columns = ", ".join(table["columns"][:30])
                lines.append(
                    f"  - Table/sheet `{table['name']}` rows={table['row_count']} "
                    f"columns={columns}"
                )
        if not sources:
            lines.append("- No contract database is configured.")
        lines.extend(["", "## Uploaded contract documents", ""])
        if not copied_documents:
            lines.append("- No uploaded contract documents are attached to this chat.")
        for item in copied_documents:
            lines.append(f"- `{item['workspace_path']}`: {item['name']}")
            if item.get("extracted_text_workspace_path"):
                lines.append(f"  - Extracted text: `{item['extracted_text_workspace_path']}`")
            if item["status"] != "copied":
                lines.append(f"  - Warning: {item['error']}")
        manifest = data_dir / "DATA_MANIFEST.md"
        manifest.write_text("\n".join(lines), encoding="utf-8")
        (data_dir / "scratch").mkdir(exist_ok=True)
        return manifest

    def _build_prompt(
        self,
        question: str,
        messages: list[dict[str, str]],
        copied_files: list[dict[str, Any]],
        manifest: Path,
    ) -> str:
        recent_context = "\n".join(
            f"{message.get('role', 'unknown')}: {message.get('content', '')[:1600]}"
            for message in messages[-6:]
        )
        file_list = "\n".join(
            f"- {item['workspace_path']} ({item['source_type']}, {item['name']})"
            for item in copied_files
        )
        if not file_list:
            file_list = "- No copied data files are available."
        return f"""You are the Advanced Intelligence Engine inside Chat with Contracts.

The user asked:
{question}

You are running from a data-only working directory. The only approved inputs are
the files listed below and the local manifest `{manifest.name}`. The files may be
the generated SQLite contract database and uploaded contract documents.

Hard boundaries:
- Answer only questions about contracts using the generated contract database and,
  when present, the uploaded contract documents.
- Prefer querying the SQLite contract database for structured facts. Use uploaded
  contract documents only as supporting evidence or when the question requires
  language/details that are not in the database.
- If the user asks about the local filesystem, parent folders, system state,
  installed software, secrets, credentials, source code, unrelated files, or any
  non-contract task, do not perform it. Ask the user to provide a contract question
  instead.
- Do not inspect `..`, absolute paths, home folders, system folders, network
  locations, hidden configuration folders, or any file outside the current
  working directory.
- Do not use the internet.
- Do not modify original source files. Use `./scratch` only for temporary
  scripts, charts, or derived outputs.
- Prefer deterministic local analysis using SQL/Python over guessing. For SQLite,
  use read-only connections where possible.

Available copied files:
{file_list}

Recent conversation context:
{recent_context or "No recent conversation context."}

Answer the user's question clearly for a corporate business user. If you run code,
summarize the important steps and include concise tables or chart descriptions when
useful. End with a section that starts exactly with `FINAL ANSWER:`. The
`FINAL ANSWER:` section must contain the complete user-facing answer, including
any tables, recommendations, caveats, or document-specific clauses needed to
answer the question. Do not place the detailed answer only before `FINAL ANSWER:`.
Do not emit XML-style file tags such as `<file>` or `</file>`."""

    def _build_command(self, prompt: str) -> list[str]:
        command = self._command_from_setting(self.settings.qwen_command)
        command.append("--bare")
        command.extend(["--output-format", "text"])
        command.extend(["--append-system-prompt", self._data_only_system_prompt()])
        if self.settings.qwen_auth_type:
            command.extend(["--auth-type", self.settings.qwen_auth_type])
        if self.settings.qwen_model:
            command.extend(["--model", self.settings.qwen_model])
        if self.settings.qwen_approval_mode:
            command.extend(["--approval-mode", self.settings.qwen_approval_mode])
        if self.settings.qwen_use_sandbox:
            command.append("--sandbox")
        command.extend(["--include-directories", "."])
        command.extend(["-p", prompt])
        return command

    @staticmethod
    def _command_from_setting(value: str) -> list[str]:
        configured = value.strip()
        if not configured:
            return ["qwen"]
        configured_path = Path(configured)
        if configured_path.is_absolute() and configured_path.exists():
            return [configured]
        parsed = shlex.split(configured)
        return parsed or ["qwen"]

    def _process_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["OPENAI_BASE_URL"] = self.settings.llm_base_url
        env["OPENAI_API_KEY"] = self.settings.openai_api_key
        env["OPENAI_MODEL"] = self.settings.qwen_model or self.settings.model_name
        env["DASHSCOPE_API_KEY"] = self.settings.openai_api_key
        env["QWEN_API_KEY"] = self.settings.openai_api_key
        return env

    @staticmethod
    def _data_only_system_prompt() -> str:
        return (
            "You are a contract-only analysis engine for Chat with Contracts. "
            "Use only the current working directory and the copied contract files inside it. "
            "Do not inspect parent directories, home directories, system directories, "
            "network locations, credentials, source code, or unrelated files. "
            "Answer only questions about the generated SQLite contract database and "
            "uploaded contract documents. For any non-contract request, ask the user "
            "to provide a contract question."
        )

    @staticmethod
    def _safe_filename(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
        return cleaned[:80] or "data_source"

    @staticmethod
    def _clean_output(text: str) -> str:
        return ANSI_ESCAPE_RE.sub("", text).replace("\r", "")

    @staticmethod
    def _extract_answer(raw_output: str) -> str:
        raw_output = QwenCliEngine._strip_engine_artifacts(raw_output)
        marker = "FINAL ANSWER:"
        if marker not in raw_output:
            return raw_output.strip()
        extracted = raw_output.rsplit(marker, 1)[-1].strip()
        return QwenCliEngine._strip_engine_artifacts(extracted)

    @staticmethod
    def _strip_engine_artifacts(text: str) -> str:
        return (
            text.replace("<file>", "")
            .replace("</file>", "")
            .replace("<result>", "")
            .replace("</result>", "")
            .strip()
        )
