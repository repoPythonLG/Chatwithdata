from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.graph import DataChatAgent, status_event
from app.agent.qwen_cli_engine import QwenCliEngine, QwenCliResult
from app.agent.state import AgentState
from app.agent.text_sanitizer import (
    sanitize_status_events,
    sanitize_user_text,
    sanitize_user_text_list,
)
from app.core.llm import LLMClient
from app.core.runtime_settings import RuntimeSettingsService, settings_from_effective
from app.db.models import ChatMessage, Conversation
from app.schemas.chat import ChatRequest, ChatResponse, ConversationOut


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


class ChatService:
    def __init__(self, session: AsyncSession, llm: LLMClient | None = None):
        self.session = session
        self.llm = llm

    async def list_conversations(self) -> list[ConversationOut]:
        result = await self.session.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .order_by(Conversation.updated_at.desc())
            .limit(50)
        )
        conversations = list(result.scalars().unique().all())
        return [ConversationOut.model_validate(item) for item in conversations]

    async def get_conversation(self, conversation_id: str) -> ConversationOut:
        conversation = await self._get_conversation(conversation_id)
        return ConversationOut.model_validate(conversation)

    async def delete_conversation(self, conversation_id: str) -> None:
        conversation = await self.session.get(Conversation, conversation_id)
        if conversation is None:
            return
        await self.session.delete(conversation)
        await self.session.commit()

    async def clear_conversations(self) -> None:
        await self.session.execute(delete(ChatMessage))
        await self.session.execute(delete(Conversation))
        await self.session.commit()

    async def run_chat(self, payload: ChatRequest) -> ChatResponse:
        conversation = await self._ensure_conversation(payload)
        user_message = ChatMessage(
            conversation_id=conversation.id,
            role="user",
            content=payload.message,
            payload={
                "selected_data_sources": payload.selected_data_sources,
                "engine": payload.engine,
            },
        )
        self.session.add(user_message)
        await self.session.commit()

        context = await self._message_context(conversation.id)
        if payload.engine == "qwen_cli":
            effective_settings = await RuntimeSettingsService(self.session).get_effective()
            result = await QwenCliEngine(
                self.session, settings_from_effective(effective_settings)
            ).run(
                question=payload.message,
                messages=context,
                selected_data_sources=payload.selected_data_sources,
            )
            response = self._response_from_qwen_result(conversation.id, result)
            await self._store_assistant_message(conversation.id, response)
            return response

        agent = DataChatAgent(self.session, self.llm or await self._runtime_llm())
        final_state = await agent.run(
            AgentState(
                conversation_id=conversation.id,
                user_question=payload.message,
                messages=context,
                selected_data_sources=payload.selected_data_sources,
            )
        )
        response = self._response_from_state(conversation.id, final_state)
        await self._store_assistant_message(conversation.id, response)
        return response

    async def stream_chat(self, payload: ChatRequest) -> AsyncIterator[str]:
        conversation = await self._ensure_conversation(payload)
        user_message = ChatMessage(
            conversation_id=conversation.id,
            role="user",
            content=payload.message,
            payload={
                "selected_data_sources": payload.selected_data_sources,
                "engine": payload.engine,
            },
        )
        self.session.add(user_message)
        await self.session.commit()

        yield sse_event("conversation", {"conversation_id": conversation.id})

        context = await self._message_context(conversation.id)
        if payload.engine == "qwen_cli":
            events: list[dict[str, Any]] = []

            def emit_status(step: str, status: str, message: str, **metadata: Any) -> str:
                event = status_event(step, status, message, **metadata)
                events.append(event)
                return sse_event("status", event)

            yield emit_status(
                "Intelligence Engine",
                "running",
                "Preparing Intelligence Engine workspace.",
            )
            final_result: QwenCliResult | None = None
            effective_settings = await RuntimeSettingsService(self.session).get_effective()
            engine = QwenCliEngine(
                self.session, settings_from_effective(effective_settings)
            )
            async for event in engine.stream(
                question=payload.message,
                messages=context,
                selected_data_sources=payload.selected_data_sources,
            ):
                if event.kind == "status":
                    yield emit_status(
                        "Intelligence Engine",
                        "running",
                        event.message,
                    )
                elif event.kind == "output":
                    yield sse_event("qwen_output", {"content": event.content})
                elif event.result is not None:
                    final_result = event.result

            if final_result is None:
                yield emit_status(
                    "Intelligence Engine",
                    "error",
                    "Intelligence Engine did not produce a result.",
                )
                yield sse_event(
                    "error", {"detail": "Intelligence Engine did not produce a result."}
                )
                return

            yield emit_status(
                "Intelligence Engine",
                "completed" if final_result.ok else "error",
                (
                    "Intelligence Engine completed."
                    if final_result.ok
                    else final_result.error or "Intelligence Engine failed."
                ),
                exit_code=final_result.exit_code,
                duration_ms=final_result.duration_ms,
            )
            response = self._response_from_qwen_result(conversation.id, final_result, events)
            for token in self._tokenize_for_stream(response.answer):
                yield sse_event("token", {"content": token})
                await asyncio.sleep(0)
            stored = await self._store_assistant_message(conversation.id, response)
            response.message_id = stored.id
            yield sse_event("final", response.model_dump(mode="json"))
            return

        agent = DataChatAgent(self.session, self.llm or await self._runtime_llm())
        seen_events = 0
        final_state: AgentState | None = None
        async for state in agent.stream_states(
            AgentState(
                conversation_id=conversation.id,
                user_question=payload.message,
                messages=context,
                selected_data_sources=payload.selected_data_sources,
            )
        ):
            final_state = state
            events = state.get("status_events", [])
            for event in events[seen_events:]:
                yield sse_event("status", event)
            seen_events = len(events)

        if final_state is None:
            yield sse_event("error", {"detail": "Agent did not produce a response."})
            return

        response = self._response_from_state(conversation.id, final_state)
        for token in self._tokenize_for_stream(response.answer):
            yield sse_event("token", {"content": token})
            await asyncio.sleep(0)
        stored = await self._store_assistant_message(conversation.id, response)
        response.message_id = stored.id
        yield sse_event("final", response.model_dump(mode="json"))

    async def _ensure_conversation(self, payload: ChatRequest) -> Conversation:
        if payload.conversation_id:
            existing = await self.session.get(Conversation, payload.conversation_id)
            if existing is not None:
                return existing

        title = payload.message.strip().splitlines()[0][:80] or "New conversation"
        conversation = Conversation(id=payload.conversation_id or str(uuid.uuid4()), title=title)
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def _get_conversation(self, conversation_id: str) -> Conversation:
        result = await self.session.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )
        conversation = result.scalars().unique().one_or_none()
        if conversation is None:
            raise ValueError(f"Unknown conversation: {conversation_id}")
        return conversation

    async def _message_context(self, conversation_id: str) -> list[dict[str, str]]:
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(12)
        )
        rows = list(reversed(result.scalars().all()))
        return [{"role": row.role, "content": self._context_content(row)} for row in rows]

    @staticmethod
    def _context_content(row: ChatMessage) -> str:
        if row.role != "assistant" or not row.payload:
            return sanitize_user_text(row.content) if row.role == "assistant" else row.content

        payload = row.payload
        compact: dict[str, Any] = {}
        if payload.get("sql_query"):
            compact["sql_query"] = payload["sql_query"]
        if payload.get("sources"):
            compact["sources"] = payload["sources"][:8]

        artifacts = []
        for artifact in payload.get("artifacts", [])[:3]:
            if artifact.get("type") != "table":
                continue
            artifacts.append(
                {
                    "title": artifact.get("title"),
                    "columns": artifact.get("columns", [])[:20],
                    "rows": artifact.get("rows", [])[:8],
                    "truncated": artifact.get("truncated", False),
                }
            )
        if artifacts:
            compact["table_artifacts"] = artifacts

        if not compact:
            return row.content

        return (
            f"{row.content}\n\n"
            "[Prior assistant result context for follow-up resolution]\n"
            f"{json.dumps(compact, default=str)}"
        )

    async def _store_assistant_message(
        self, conversation_id: str, response: ChatResponse
    ) -> ChatMessage:
        message = ChatMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=response.answer,
            payload=response.model_dump(mode="json"),
        )
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def _runtime_llm(self) -> LLMClient:
        effective = await RuntimeSettingsService(self.session).get_effective()
        return LLMClient(settings_from_effective(effective))

    @staticmethod
    def _response_from_state(conversation_id: str, state: AgentState) -> ChatResponse:
        final = state.get("final_response") or {}
        status_events = sanitize_status_events(
            final.get("status_events") or state.get("status_events", [])
        )
        return ChatResponse(
            conversation_id=conversation_id,
            answer=sanitize_user_text(final.get("answer") or "I could not produce an answer."),
            reasoning_summary=sanitize_user_text(final.get("reasoning_summary") or ""),
            sql_query=final.get("sql_query"),
            python_code=final.get("python_code"),
            artifacts=final.get("artifacts") or [],
            sources=final.get("sources") or [],
            caveats=sanitize_user_text_list(final.get("caveats") or []),
            confidence=final.get("confidence") or "medium",
            status_events=status_events,
        )

    @staticmethod
    def _response_from_qwen_result(
        conversation_id: str,
        result: QwenCliResult,
        status_events: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        caveats = [
            (
                "The Intelligence Engine can create and inspect files inside "
                "its isolated run workspace."
            ),
            (
                "Only copied data files were provided to the engine workspace; "
                "original source files were not modified."
            ),
        ]
        if result.error:
            caveats.append(result.error)
        return ChatResponse(
            conversation_id=conversation_id,
            answer=sanitize_user_text(result.answer),
            reasoning_summary=(
                "Used the Intelligence Engine against copied data files in an isolated "
                "workspace. Raw engine output is available in Advanced mode."
            ),
            qwen_output=sanitize_user_text(result.raw_output),
            qwen_workspace=result.workspace,
            sources=[
                {
                    "data_source_id": item.get("id"),
                    "data_source_name": item.get("name"),
                    "table": item.get("workspace_path"),
                    "columns": [],
                }
                for item in result.files
            ],
            caveats=caveats,
            confidence="medium" if result.ok else "low",
            status_events=sanitize_status_events(status_events or []),
        )

    @staticmethod
    def _tokenize_for_stream(text: str) -> list[str]:
        if not text:
            return []
        parts = text.split(" ")
        return [part + (" " if index < len(parts) - 1 else "") for index, part in enumerate(parts)]
