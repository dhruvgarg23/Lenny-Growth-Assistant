from app.services.prompts import build_grounded_messages, build_ship30_messages, build_artifact_messages

def test_grounded_includes_citations_instruction():
    msgs = build_grounded_messages("what is onboarding?", [], [{"title":"T","guest":"G","source_path":"podcasts/a.md","content":"activation matters"}])
    assert any("source: path" in m["content"] for m in msgs)
    assert any("CONTEXT" in m["content"] for m in msgs)

def test_ship30_has_headline_and_citations():
    msgs = build_ship30_messages("onboarding activation", [], [{"title":"Onboarding","guest":"Elena Verna","source_path":"podcasts/elena.md","content":"loops"}])
    sys = msgs[0]["content"]
    assert "Ship 30" in sys
    assert "1,250" in sys

def test_artifact_html_has_safety_rules():
    msgs = build_artifact_messages("make one-pager", [], [{"title":"T","source_path":"podcasts/a.md","content":"x"}], "html")
    sys = msgs[0]["content"]
    assert "<script>" not in sys or "Do NOT include <script>" in sys
    assert "cite" in sys.lower()
