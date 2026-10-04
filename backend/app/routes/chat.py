"""Chat transport adapter — formats the conversation module's domain events as SSE.

All pipeline logic (mode, retrieval, abstention, artifacts, persistence) lives in
app.services.conversation. This module only maps HTTP ↔ events.
"""
import json
from functools import partial
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import runtime
from app.services.database import get_db
from app.models.schemas import ChatRequest
from app.services.retrieval import hybrid_search
from app.services import llm as llm_service
from app.services.agent_router import detect_artifact_type
from app.services.conversation import (
    AnswerRequest,
    ArtifactReady,
    Done,
    Failed,
    Grounded,
    Refused,
    Retrieving,
    Token,
    SqlAlchemyStore,
    answer,
)
from app.observability.logger import get_logger, bind, unbind

logger = get_logger("lenny.chat")
router = APIRouter(prefix="/sessions/{session_id}/chat", tags=["chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class ServiceLlm:
    """Llm adapter: provider knowledge stays in app.services.llm."""

    @property
    def identity(self) -> tuple[str, str]:
        return runtime.provider, runtime.model

    async def check_available(self) -> tuple[bool, str | None]:
        return await llm_service.check_available()

    async def stream_tokens(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        async for tok in llm_service.stream(messages):
            yield tok


def _format(ev, req: AnswerRequest) -> list[str]:
    """Map one domain event to zero or more SSE frames."""
    if isinstance(ev, Retrieving):
        return [_sse("status", {"stage": "retrieving", "message": "Searching Lenny transcripts…"})]
    if isinstance(ev, Grounded):
        return [
            _sse("sources", {"sources": [s.__dict__ for s in ev.sources], "confidence": ev.confidence}),
            _sse("status", {"stage": "generating", "message": "Drafting answer…"}),
        ]
    if isinstance(ev, Token):
        return [_sse("token", {"delta": ev.delta})]
    if isinstance(ev, ArtifactReady):
        return [_sse("artifact", {"artifact": ev.artifact.__dict__})]
    if isinstance(ev, Refused):
        return [
            _sse("sources", {"sources": [], "confidence": ev.confidence, "abstained": True}),
            _sse("token", {"delta": ev.content}),
        ]
    if isinstance(ev, Done):
        r = ev.result
        return [_sse("done", {
            "latency_ms": r.latency_ms,
            "sources": [s.__dict__ for s in r.sources],
            "mode": req.mode,
            "artifact": r.artifact.__dict__ if r.artifact else None,
            "confidence": r.confidence,
            "abstained": r.abstained,
            "provider": r.provider,
            "model": r.model,
            "request_id": req.request_id,
        })]
    if isinstance(ev, Failed):
        return [_sse("error", {
            "detail": ev.detail,
            "error_code": ev.error_code,
            "request_id": req.request_id,
            "provider": ev.provider,
            "model": ev.model,
        })]
    logger.warning(f"unknown_conversation_event type={type(ev).__name__}")
    return []


@router.post("/stream")
async def chat_stream(session_id: str, payload: ChatRequest, request: Request, db: AsyncSession = Depends(get_db)):
    request_id = getattr(request.state, "request_id", "-")
    tokens = bind(session_id=session_id, request_id=request_id, provider=runtime.provider, model=runtime.model)

    try:
        store = SqlAlchemyStore(db)
        if await store.title(session_id) is None:
            logger.warning(f"session_not_found session_id={session_id}", extra={"event": "session_not_found"})
            raise HTTPException(status_code=404, detail="Session not found or expired")

        # Explicit mode always wins; chat means chat (no keyword override).
        artifact_type = (
            detect_artifact_type(payload.message, payload.artifact_type)
            if payload.mode == "artifact" else None
        )
        req = AnswerRequest(
            question=payload.message,
            session_id=session_id,
            mode=payload.mode,
            artifact_type=artifact_type,
            request_id=request_id,
        )
        logger.info(
            f"chat_stream_received mode={req.mode} artifact_type={artifact_type}",
            extra={"event": "chat_stream_start", "mode": req.mode,
                   "artifact_type": artifact_type, "msg_preview": payload.message[:60]},
        )

        async def event_gen() -> AsyncGenerator[str, None]:
            async for ev in answer(
                req, store=store,
                retriever=partial(hybrid_search, db),
                llm=ServiceLlm(),
            ):
                for frame in _format(ev, req):
                    yield frame

        return StreamingResponse(
            event_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                     "Connection": "keep-alive", "X-Request-ID": request_id},
        )
    finally:
        unbind(tokens)
