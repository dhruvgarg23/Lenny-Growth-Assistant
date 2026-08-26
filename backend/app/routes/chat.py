import json
import time
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings, runtime
from app.services.database import get_db
from app.models.db import Session, Message
from app.models.schemas import ChatRequest
from app.services.retrieval import hybrid_search
from app.services.prompts import build_grounded_messages, build_ship30_messages, build_artifact_messages
from app.services.llm import generate, stream, ollama_health
from app.services.agent_router import route_intent, detect_artifact_type
from app.services.artifacts import sanitize_html
from app.observability.logger import get_logger, bind, unbind, Timer

logger = get_logger("lenny.chat")
router = APIRouter(prefix="/sessions/{session_id}/chat", tags=["chat"])

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

async def _load_history(db: AsyncSession, session_id: str) -> list[dict]:
    q = await db.execute(select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc()).limit(20))
    msgs = q.scalars().all()
    return [{"role": m.role, "content": m.content} for m in msgs]

@router.post("/stream")
async def chat_stream(session_id: str, payload: ChatRequest, request: Request, db: AsyncSession = Depends(get_db)):
    request_id = getattr(request.state, "request_id", "-")
    tokens = bind(session_id=session_id, request_id=request_id, provider=runtime.provider, model=runtime.model)

    try:
        sess = await db.get(Session, session_id)
        if not sess:
            logger.warning(f"session_not_found session_id={session_id}", extra={"event": "session_not_found"})
            raise HTTPException(status_code=404, detail="Session not found or expired")

        # Pre-check provider availability (Ollama)
        if runtime.provider == "ollama":
            ok = await ollama_health()
            if not ok:
                logger.warning("ollama_unreachable_stream_abort", extra={"event": "provider_unreachable", "provider": "ollama"})
                async def _err_gen():
                    yield _sse("error", {
                        "detail": "Ollama is not reachable at OLLAMA_BASE_URL. Start it with: ollama serve && ollama pull llm_model",
                        "error_code": "PROVIDER_UNREACHABLE",
                        "request_id": request_id,
                        "provider": runtime.status(),
                    })
                return StreamingResponse(_err_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        mode = route_intent(payload.message, payload.mode if payload.mode != "chat" else None)
        if payload.mode in ("ship30", "artifact"):
            mode = payload.mode
        artifact_type = detect_artifact_type(payload.message, payload.artifact_type) if mode == "artifact" else None

        logger.info(
            f"chat_stream_received mode={mode} artifact_type={artifact_type}",
            extra={"event": "chat_stream_start", "mode": mode, "artifact_type": artifact_type, "msg_preview": payload.message[:60]},
        )

        # Persist user message first
        user_msg = Message(session_id=session_id, role="user", content=payload.message, meta={"mode": mode, "artifact_type": artifact_type})
        db.add(user_msg)
        await db.flush()
        if sess.title in ("New chat", ""):
            sess.title = payload.message[:60]

        async def event_gen() -> AsyncGenerator[str, None]:
            t0 = time.perf_counter()
            try:
                yield _sse("status", {"stage": "retrieving", "message": "Searching Lenny transcripts…"})
                history = await _load_history(db, session_id)

                with Timer() as ret_timer:
                    try:
                        contexts = await hybrid_search(db, payload.message)
                    except Exception as e:
                        logger.exception(f"Retrieval error: {e}")
                        contexts = []

                top_conf = contexts[0]["rrf_score"] if contexts else 0.0
                if not contexts or top_conf < settings.rag_min_confidence:
                    logger.info(
                        f"chat_abstained top_conf={top_conf:.4f} < min={settings.rag_min_confidence}",
                        extra={"event": "chat_abstention", "top_conf": top_conf, "threshold": settings.rag_min_confidence},
                    )
                    yield _sse("sources", {"sources": [], "confidence": top_conf, "abstained": True})
                    abstain = "I don't have support in the available Lenny transcripts for that. Try asking about product strategy, onboarding, PLG, pricing, or retention — e.g., 'What does Lenny's Podcast say about onboarding activation?'"
                    yield _sse("token", {"delta": abstain})
                    
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    msg = Message(session_id=session_id, role="assistant", content=abstain, meta={"sources": [], "confidence": top_conf, "abstained": True, "mode": mode, "latency_ms": elapsed_ms, "provider": runtime.provider, "model": runtime.model})
                    db.add(msg)
                    await db.commit()
                    yield _sse("done", {
                        "latency_ms": elapsed_ms,
                        "sources": [],
                        "abstained": True,
                        "request_id": request_id,
                        "provider": runtime.provider,
                        "model": runtime.model,
                    })
                    return

                sources = [
                    {"document_id": c["document_id"], "chunk_id": c["id"], "source_path": c["source_path"], "title": c["title"], "guest": c["guest"], "score": c["rrf_score"], "excerpt": c["content"][:280]}
                    for c in contexts
                ]
                yield _sse("sources", {"sources": sources, "confidence": top_conf})
                yield _sse("status", {"stage": "generating", "message": "Drafting answer…"})

                if mode == "ship30":
                    messages = build_ship30_messages(payload.message, history, contexts)
                elif mode == "artifact":
                    messages = build_artifact_messages(payload.message, history, contexts, artifact_type)
                else:
                    messages = build_grounded_messages(payload.message, history, contexts)

                full = ""
                async for delta in stream(messages):
                    if delta:
                        full += delta
                        yield _sse("token", {"delta": delta})

                artifact = None
                if mode == "artifact":
                    raw = full
                    if artifact_type == "html":
                        sanitized, warnings = sanitize_html(raw)
                        if "```" in raw:
                            import re
                            m = re.search(r"```html(.*?)```", raw, flags=re.S|re.I)
                            if m:
                                raw = m.group(1)
                                sanitized, warnings = sanitize_html(raw)
                        artifact = {"type": "html", "content": sanitized, "raw": raw[:200000], "warnings": warnings}
                        yield _sse("artifact", {"artifact": artifact})
                        full = sanitized
                    else:
                        import re
                        m = re.search(r"```markdown(.*?)```", raw, flags=re.S|re.I)
                        if m:
                            raw = m.group(1).strip()
                        artifact = {"type": "markdown", "content": raw, "warnings": []}
                        yield _sse("artifact", {"artifact": artifact})
                        full = raw

                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                meta = {
                    "sources": sources,
                    "confidence": top_conf,
                    "mode": mode,
                    "artifact": artifact,
                    "latency_ms": elapsed_ms,
                    "provider": runtime.provider,
                    "model": runtime.model,
                    "request_id": request_id,
                }
                msg = Message(session_id=session_id, role="assistant", content=full, meta=meta)
                db.add(msg)
                await db.commit()

                logger.info(
                    f"chat_stream_completed duration_ms={elapsed_ms} sources={len(sources)} chars={len(full)}",
                    extra={"event": "chat_stream_done", "duration_ms": elapsed_ms, "sources_count": len(sources), "response_chars": len(full)},
                )

                yield _sse("done", {
                    "latency_ms": elapsed_ms,
                    "sources": sources,
                    "mode": mode,
                    "artifact": artifact,
                    "confidence": top_conf,
                    "provider": runtime.provider,
                    "model": runtime.model,
                    "request_id": request_id,
                })
            except Exception as e:
                logger.exception(f"Chat stream error: {e}")
                yield _sse("error", {
                    "detail": str(e),
                    "request_id": request_id,
                    "provider": runtime.provider,
                    "model": runtime.model,
                })
                try:
                    await db.rollback()
                except Exception:
                    pass

        return StreamingResponse(
            event_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive", "X-Request-ID": request_id},
        )
    finally:
        unbind(tokens)

@router.post("")
async def chat_non_stream(session_id: str, payload: ChatRequest, request: Request, db: AsyncSession = Depends(get_db)):
    request_id = getattr(request.state, "request_id", "-")
    tokens = bind(session_id=session_id, request_id=request_id, provider=runtime.provider, model=runtime.model)

    t0 = time.perf_counter()
    try:
        sess = await db.get(Session, session_id)
        if not sess:
            raise HTTPException(status_code=404, detail="Session not found")
        if runtime.provider == "ollama":
            ok = await ollama_health()
            if not ok:
                raise HTTPException(status_code=503, detail="Ollama not reachable. Start with: ollama serve && ollama pull llm_model")

        mode = route_intent(payload.message, payload.mode if payload.mode != "chat" else None)
        if payload.mode in ("ship30", "artifact"):
            mode = payload.mode
        artifact_type = detect_artifact_type(payload.message, payload.artifact_type) if mode == "artifact" else None

        user_msg = Message(session_id=session_id, role="user", content=payload.message, meta={"mode": mode})
        db.add(user_msg)
        await db.flush()
        if sess.title in ("New chat", ""):
            sess.title = payload.message[:60]
        history = await _load_history(db, session_id)
        contexts = await hybrid_search(db, payload.message)
        top_conf = contexts[0]["rrf_score"] if contexts else 0.0

        if not contexts or top_conf < settings.rag_min_confidence:
            abstain = "I don't have support in the available Lenny transcripts for that. Try asking about product strategy, onboarding, PLG, pricing, or retention."
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            msg = Message(session_id=session_id, role="assistant", content=abstain, meta={"sources": [], "confidence": top_conf, "abstained": True, "mode": mode, "latency_ms": elapsed_ms})
            db.add(msg)
            await db.commit()
            return {"content": abstain, "sources": [], "abstained": True, "mode": mode, "request_id": request_id, "latency_ms": elapsed_ms}

        if mode == "ship30":
            messages = build_ship30_messages(payload.message, history, contexts)
        elif mode == "artifact":
            messages = build_artifact_messages(payload.message, history, contexts, artifact_type)
        else:
            messages = build_grounded_messages(payload.message, history, contexts)

        sources = [{"document_id": c["document_id"], "chunk_id": c["id"], "source_path": c["source_path"], "title": c["title"], "guest": c["guest"], "score": c["rrf_score"]} for c in contexts]
        text_out = await generate(messages)

        artifact = None
        if mode == "artifact" and artifact_type == "html":
            sanitized, warnings = sanitize_html(text_out)
            artifact = {"type": "html", "content": sanitized, "raw": text_out[:200000], "warnings": warnings}
            text_out = sanitized
        elif mode == "artifact":
            artifact = {"type": "markdown", "content": text_out, "warnings": []}

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        msg = Message(session_id=session_id, role="assistant", content=text_out, meta={"sources": sources, "confidence": top_conf, "mode": mode, "artifact": artifact, "latency_ms": elapsed_ms, "provider": runtime.provider, "model": runtime.model, "request_id": request_id})
        db.add(msg)
        await db.commit()
        return {
            "content": text_out,
            "sources": sources,
            "mode": mode,
            "artifact": artifact,
            "confidence": top_conf,
            "provider": runtime.provider,
            "model": runtime.model,
            "request_id": request_id,
            "latency_ms": elapsed_ms,
        }
    finally:
        unbind(tokens)
