"""Seam-level tests for the conversation module.

Every test crosses only answer() with a fake store / retriever / llm —
no DB, no network, no provider keys.
"""
from app.services.retrieval import Passage
from app.services.conversation import (
    ABSTAIN_TEXT,
    AnswerRequest,
    ArtifactReady,
    Done,
    Failed,
    Grounded,
    Refused,
    Retrieving,
    Token,
    answer,
)


def make_chunk(score, cid="c1"):
    return Passage(
        id=cid,
        document_id="d1",
        source_path="podcasts/guest.md",
        title="Episode",
        guest="Guest",
        content="x" * 500,
        rrf_score=score,
    )


class FakeStore:
    def __init__(self):
        self.user_msgs = []
        self.assistant_msgs = []
        self.title_state = "New chat"
        self.commits = 0
        self.rollbacks = 0

    async def title(self, session_id):
        return self.title_state

    async def save_user_message(self, session_id, content, mode, artifact_type):
        self.user_msgs.append({"content": content, "mode": mode})

    async def update_title_from_question(self, session_id, question):
        if self.title_state in ("New chat", ""):
            self.title_state = question[:60]

    async def load_history(self, session_id, limit=20):
        return []

    async def save_assistant_message(self, session_id, content, meta):
        self.assistant_msgs.append({"content": content, "meta": meta})

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class FakeLlm:
    def __init__(self, tokens=(), available=True):
        self.tokens = list(tokens)
        self.available = available

    @property
    def identity(self):
        return "fake", "fake-1"

    async def check_available(self):
        return (self.available, None if self.available else "fake provider down")

    async def stream_tokens(self, messages):
        for t in self.tokens:
            yield t


async def collect(req, store=None, retriever=None, llm=None):
    store = store or FakeStore()
    retriever = retriever or (lambda q: _const([]))
    llm = llm or FakeLlm(["Hello", " world"])
    events = [e async for e in answer(req, store=store, retriever=retriever, llm=llm)]
    return events, store


async def _const(v):
    return v


def req(**kw):
    base = {"question": "How to improve onboarding?", "session_id": "s1"}
    base.update(kw)
    return AnswerRequest(**base)


async def test_happy_chat_streams_tokens_then_done():
    events, store = await collect(
        req(), retriever=lambda q: _const([make_chunk(0.05)])
    )
    assert isinstance(events[0], Retrieving)
    assert isinstance(events[1], Grounded)
    assert [e.delta for e in events if isinstance(e, Token)] == ["Hello", " world"]
    done = next(e for e in events if isinstance(e, Done))
    assert done.result.content == "Hello world"
    assert done.result.abstained is False
    assert done.result.provider == "fake"
    # persistence owned by the module
    assert store.commits == 1
    assert len(store.user_msgs) == 1
    assert store.assistant_msgs[0]["content"] == "Hello world"
    meta = store.assistant_msgs[0]["meta"]
    assert meta["mode"] == "chat" and meta["provider"] == "fake"


async def test_sources_always_carry_excerpts():
    events, _ = await collect(
        req(), retriever=lambda q: _const([make_chunk(0.05)])
    )
    grounded = next(e for e in events if isinstance(e, Grounded))
    assert len(grounded.sources) == 1
    assert len(grounded.sources[0].excerpt) == 280


async def test_empty_retrieval_abstains_with_canon_text():
    events, store = await collect(req(), retriever=lambda q: _const([]))
    assert isinstance(events[0], Retrieving)
    refused = next(e for e in events if isinstance(e, Refused))
    assert refused.content == ABSTAIN_TEXT
    done = next(e for e in events if isinstance(e, Done))
    assert done.result.abstained is True
    meta = store.assistant_msgs[0]["meta"]
    # full meta even on the abstention path
    assert meta["abstained"] is True
    assert meta["provider"] == "fake" and meta["model"] == "fake-1"
    assert meta["request_id"] == "-"


async def test_low_confidence_abstains():
    events, _ = await collect(
        req(), retriever=lambda q: _const([make_chunk(0.001)])
    )
    assert any(isinstance(e, Refused) for e in events)
    assert not any(isinstance(e, Token) for e in events)


async def test_retriever_error_degrades_to_abstention():
    async def boom(q):
        raise RuntimeError("db gone")

    events, _ = await collect(req(), retriever=boom)
    assert any(isinstance(e, Refused) for e in events)


async def test_explicit_mode_flows_through_untouched():
    # "essay" in a chat-mode question must NOT become ship30 (old hijack bug).
    events, store = await collect(
        req(question="Write an essay about onboarding?", mode="chat"),
        retriever=lambda q: _const([make_chunk(0.05)]),
    )
    assert store.user_msgs[0]["mode"] == "chat"
    assert store.assistant_msgs[0]["meta"]["mode"] == "chat"
    assert any(isinstance(e, Done) for e in events)


async def test_artifact_html_extracts_fence_then_sanitizes_once():
    events, store = await collect(
        req(mode="artifact", artifact_type="html"),
        retriever=lambda q: _const([make_chunk(0.05)]),
        llm=FakeLlm(['```html<h1>Hi</h1><script>evil()</script>```']),
    )
    ready = next(e for e in events if isinstance(e, ArtifactReady))
    assert ready.artifact.type == "html"
    assert "<script>" not in ready.artifact.content
    assert "```" not in ready.artifact.content
    assert store.assistant_msgs[0]["content"] == ready.artifact.content


async def test_provider_unavailable_yields_failed():
    events, store = await collect(req(), llm=FakeLlm(available=False))
    failed = next(e for e in events if isinstance(e, Failed))
    assert failed.error_code == "PROVIDER_UNREACHABLE"
    assert store.commits == 0
