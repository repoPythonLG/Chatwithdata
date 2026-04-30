from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.service import ChatService
from app.db.session import get_session
from app.schemas.chat import ChatRequest, ChatResponse, ConversationOut

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("", response_model=list[ConversationOut])
async def list_conversations(session: AsyncSession = Depends(get_session)):
    return await ChatService(session).list_conversations()


@router.post("", response_model=ChatResponse)
async def create_chat(payload: ChatRequest, session: AsyncSession = Depends(get_session)):
    return await ChatService(session).run_chat(payload)


@router.post("/stream")
async def stream_chat(payload: ChatRequest, session: AsyncSession = Depends(get_session)):
    return StreamingResponse(
        ChatService(session).stream_chat(payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(conversation_id: str, session: AsyncSession = Depends(get_session)):
    try:
        return await ChatService(session).get_conversation(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{conversation_id}/messages", response_model=ChatResponse)
async def append_message(
    conversation_id: str,
    payload: ChatRequest,
    session: AsyncSession = Depends(get_session),
):
    payload.conversation_id = conversation_id
    return await ChatService(session).run_chat(payload)
