from app.services.agent_router import route_intent, detect_artifact_type

def test_route_chat_default():
    assert route_intent("How do I improve retention?") == "chat"

def test_route_explicit_mode_wins():
    # Explicit mode always wins; the pipeline uses payload.mode directly and
    # never lets keyword auto-detect override it (chat means chat).
    assert route_intent("anything", requested_mode="ship30") == "ship30"
    assert route_intent("anything ship 30", requested_mode="chat") == "chat"
    assert route_intent("render an HTML one-pager", requested_mode="chat") == "chat"

def test_detect_artifact_type_always_markdown():
    # HTML artifacts were removed; every artifact request produces Markdown.
    assert detect_artifact_type("make html artifact") == "markdown"
    assert detect_artifact_type("markdown doc") == "markdown"
    assert detect_artifact_type("anything", explicit="html") == "markdown"
    assert detect_artifact_type("no hint") == "markdown"  # default


def test_anthropic_payload_preparation():
    from app.services.llm.anthropic import prepare_anthropic_payload
    messages = [
        {"role": "system", "content": "You are Lenny Assistant."},
        {"role": "user", "content": "Hello"},
        {"role": "user", "content": "How to scale?"},
        {"role": "assistant", "content": "Focus on PMF."},
    ]
    system_prompt, convo = prepare_anthropic_payload(messages)
    assert system_prompt == "You are Lenny Assistant."
    assert len(convo) == 2  # merged adjacent user messages
    assert convo[0]["role"] == "user"
    assert "Hello\n\nHow to scale?" in convo[0]["content"]
    assert convo[1]["role"] == "assistant"


def test_runtime_config_anthropic():
    from app.config import Settings, RuntimeConfig
    s = Settings(LLM_PROVIDER="ollama", ANTHROPIC_API_KEY="")
    rt = RuntimeConfig(s)
    assert rt.is_anthropic is False
    assert "claude-3-5-sonnet-20241022" in rt.allowed_models("anthropic")
    import pytest
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not configured"):
        rt.switch("anthropic", "claude-3-5-sonnet-20241022")
