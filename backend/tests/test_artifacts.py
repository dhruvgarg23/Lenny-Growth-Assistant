from app.services.artifacts import sanitize_html, prepare_artifact, MAX_ARTIFACT_CHARS

def test_sanitize_blocks_script():
    raw = "<p>hi</p><script>alert(1)</script><div onload='x()'>x</div>"
    clean, warnings = sanitize_html(raw)
    assert "<script" not in clean.lower()
    assert "onload" not in clean.lower()
    assert len(warnings) > 0

def test_sanitize_allows_style_but_blocks_import():
    raw = "<style>@import url('http://evil.com'); body{color:red}</style><h1>Title</h1>"
    clean, warnings = sanitize_html(raw)
    assert "@import" not in clean
    # style is stripped due to forbidden pattern, but h1 remains
    assert "Title" in clean

def test_sanitize_preserves_table():
    raw = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
    clean, _ = sanitize_html(raw)
    assert "<table" in clean.lower()

def test_prepare_extracts_fence_before_single_sanitize():
    content, artifact = prepare_artifact("```html<h1>Hi</h1><script>evil()</script>```", "html")
    assert "```" not in content
    assert "<script" not in content.lower()
    assert artifact.type == "html" and artifact.raw is not None

def test_prepare_truncates_oversize_with_warning():
    content, artifact = prepare_artifact("x" * (MAX_ARTIFACT_CHARS + 100), "html")
    assert len(content) == MAX_ARTIFACT_CHARS
    assert any("truncated" in w for w in artifact.warnings)

def test_prepare_markdown_passes_through_with_fence_stripped():
    content, artifact = prepare_artifact("```markdown\n# Hello\n- item\n```", "markdown")
    assert content == "# Hello\n- item"
    assert artifact.type == "markdown" and artifact.raw is None
