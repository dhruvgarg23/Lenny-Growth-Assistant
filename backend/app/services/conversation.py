"""
Conversation module — the single pipeline behind answering a question in a session:

    resolve mode (explicit wins) → retrieve transcript chunks →
    abstain on low confidence → generate → build artifact → persist

Transports (SSE, JSON) are adapters outside this module's seam. Tests cross the
same seam via ``answer()`` with fake store / retriever / llm.

Canon (settled in architecture review):
- sources always carry excerpts
- fences are extracted *before* a single sanitize pass
- one abstention wording
- full meta on every persisted assistant message
"""
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Awaitable, Callable, Literal, Optional, Protocol, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.db import Message, Session
from app.services.retrieval import Passage
from app.services.prompts import (
    build_artifact_messages,
    build_grounded_messages,
    build_ship30_messages,
)
from app.services.artifacts import PreparedArtifact, prepare_artifact
from app.observability.logger import get_logger

logger = get_logger("lenny.conversation")

Mode = Literal["chat", "ship30", "artifact"]

ABSTAIN_TEXT = (
    "I don't have support in the available Lenny transcripts for that. "
    "Try asking about product strategy, onboarding, PLG, pricing, or retention — "
    "e.g., 'What does Lenny's Podcast say about onboarding activation?'"
)


# ── Interface types ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class AnswerRequest:
    question: str
    session_id: str
    mode: Mode = "chat"
    artifact_type: Optional[Literal["markdown", "html"]] = None
    request_id: str = "-"


@dataclass(frozen=True)
class SourceRef:
    document_id: str
    chunk_id: str
    source_path: str
    title: str
    guest: Optional[str]
    score: float
    excerpt: str


@dataclass(frozen=True)
class GroundedResult:
    content: str
    sources: tuple = ()
    artifact: Optional[PreparedArtifact] = None
    abstained: bool = False
    confidence: float = 0.0
    latency_ms: int = 0
    provider: str = ""
    model: str = ""


# Domain events yielded by answer(). The SSE adapter formats these; tests assert them.
@dataclass(frozen=True)
class Retrieving:
    pass


@dataclass(frozen=True)
class Grounded:
    sources: tuple
    confidence: float


@dataclass(frozen=True)
class Refused:
    content: str
    confidence: float


@dataclass(frozen=True)
class Token:
    delta: str


@dataclass(frozen=True)
class ArtifactReady:
    artifact: PreparedArtifact


@dataclass(frozen=True)
class Done:
    result: GroundedResult


@dataclass(frozen=True)
class Failed:
    detail: str
    error_code: str
    provider: str
    model: str


# ── Injected seams ────────────────────────────────────────────────────────────
class ConversationStore(Protocol):
    """Persistence behind the seam. Implemented by SqlAlchemyStore in prod."""

    async def title(self, session_id: str) -> Optional[str]: ...
    async def save_user_message(self, session_id: str, content: str, mode: str, artifact_type: Optional[str]) -> None: ...
    async def update_title_from_question(self, session_id: str, question: str) -> None: ...
    async def load_history(self, session_id: str, limit: int = 20) -> list[dict]: ...
    async def save_assistant_message(self, session_id: str, content: str, meta: dict) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class Llm(Protocol):
    """Generation behind the seam. Provider knowledge lives in the adapter."""

    @property
    def identity(self) -> tuple[str, str]: ...  # (provider, model)
    async def check_available(self) -> tuple[bool, Optional[str]]: ...
    def stream_tokens(self, messages: list[dict]) -> AsyncGenerator[str, None]: ...


Retriever = Callable[[str], Awaitable[Sequence[Passage]]]


class SqlAlchemyStore:
    """ConversationStore backed by an injected AsyncSession. Never reaches for get_db."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def title(self, session_id: str) -> Optional[str]:
        sess = await self._db.get(Session, session_id)
        return sess.title if sess else None

    async def save_user_message(self, session_id: str, content: str, mode: str, artifact_type: Optional[str]) -> None:
        self._db.add(Message(
            session_id=session_id, role="user", content=content,
            meta={"mode": mode, "artifact_type": artifact_type},
        ))
        await self._db.flush()

    async def update_title_from_question(self, session_id: str, question: str) -> None:
        sess = await self._db.get(Session, session_id)
        if sess is not None and sess.title in ("New chat", ""):
            sess.title = question[:60]

    async def load_history(self, session_id: str, limit: int = 20) -> list[dict]:
        q = await self._db.execute(
            select(Message).where(Message.session_id == session_id)
            .order_by(Message.created_at.asc()).limit(limit)
        )
        return [{"role": m.role, "content": m.content} for m in q.scalars().all()]

    async def save_assistant_message(self, session_id: str, content: str, meta: dict) -> None:
        self._db.add(Message(session_id=session_id, role="assistant", content=content, meta=meta))

    async def commit(self) -> None:
        await self._db.commit()

    async def rollback(self) -> None:
        try:
            await self._db.rollback()
        except Exception:
            pass


class _ProviderUnavailable(RuntimeError):
    pass


# ── Pipeline ──────────────────────────────────────────────────────────────────
def _sources(contexts: Sequence[Passage]) -> tuple[SourceRef, ...]:
    return tuple(
        SourceRef(
            document_id=c.document_id,
            chunk_id=c.id,
            source_path=c.source_path,
            title=c.title,
            guest=c.guest,
            score=c.rrf_score,
            excerpt=(c.content or "")[:280],
        )
        for c in contexts
    )


async def answer(
    req: AnswerRequest,
    *,
    store: ConversationStore,
    retriever: Retriever,
    llm: Llm,
) -> AsyncGenerator[Retrieving | Grounded | Refused | Token | ArtifactReady | Done | Failed, None]:
    """Run the conversation pipeline, yielding domain events. Owns persistence."""
    t0 = time.perf_counter()
    provider, model = llm.identity
    mode = req.mode  # explicit mode always wins; no keyword override
    artifact_type = req.artifact_type if mode == "artifact" else None

    try:
        ok, hint = await llm.check_available()
        if not ok:
            raise _ProviderUnavailable(hint or f"Provider {provider} unavailable")

        await store.save_user_message(req.session_id, req.question, mode, artifact_type)
        await store.update_title_from_question(req.session_id, req.question)

        yield Retrieving()
        history = await store.load_history(req.session_id)
        try:
            contexts = await retriever(req.question)
        except Exception as e:
            logger.exception(f"Retrieval error: {e}")
            contexts = []

        top_conf = contexts[0].rrf_score if contexts else 0.0
        elapsed = lambda: int((time.perf_counter() - t0) * 1000)  # noqa: E731

        if not contexts or top_conf < settings.rag_min_confidence:
            logger.info(
                f"chat_abstained top_conf={top_conf:.4f} < min={settings.rag_min_confidence}",
                extra={"event": "chat_abstention", "top_conf": top_conf,
                       "threshold": settings.rag_min_confidence},
            )
            meta = {"sources": [], "confidence": top_conf, "abstained": True, "mode": mode,
                    "latency_ms": elapsed(), "provider": provider, "model": model,
                    "request_id": req.request_id}
            await store.save_assistant_message(req.session_id, ABSTAIN_TEXT, meta)
            await store.commit()
            yield Refused(content=ABSTAIN_TEXT, confidence=top_conf)
            yield Done(result=GroundedResult(
                content=ABSTAIN_TEXT, abstained=True, confidence=top_conf,
                latency_ms=elapsed(), provider=provider, model=model))
            return

        sources = _sources(contexts)
        yield Grounded(sources=sources, confidence=top_conf)

        if mode == "ship30":
            messages = build_ship30_messages(req.question, history, contexts)
        elif mode == "artifact":
            messages = build_artifact_messages(req.question, history, contexts, artifact_type)
        else:
            messages = build_grounded_messages(req.question, history, contexts)

        full = ""
        async for delta in llm.stream_tokens(messages):
            if delta:
                full += delta
                yield Token(delta=delta)

        artifact = None
        if mode == "artifact":
            full, artifact = prepare_artifact(full, artifact_type or "html")
            yield ArtifactReady(artifact=artifact)

        meta = {
            "sources": [s.__dict__ for s in sources],
            "confidence": top_conf,
            "mode": mode,
            "artifact": artifact.__dict__ if artifact else None,
            "latency_ms": elapsed(),
            "provider": provider,
            "model": model,
            "request_id": req.request_id,
        }
        await store.save_assistant_message(req.session_id, full, meta)
        await store.commit()

        logger.info(
            f"chat_completed duration_ms={elapsed()} sources={len(sources)} chars={len(full)}",
            extra={"event": "chat_done", "duration_ms": elapsed(),
                   "sources_count": len(sources), "response_chars": len(full)},
        )
        yield Done(result=GroundedResult(
            content=full, sources=sources, artifact=artifact,
            confidence=top_conf, latency_ms=elapsed(),
            provider=provider, model=model))
    except Exception as e:
        logger.exception(f"Chat error: {e}")
        await store.rollback()
        code = "PROVIDER_UNREACHABLE" if isinstance(e, _ProviderUnavailable) else "UPSTREAM_ERROR"
        yield Failed(detail=str(e), error_code=code, provider=provider, model=model)
