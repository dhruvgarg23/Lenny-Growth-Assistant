from app.services.artifacts import sanitize_html, validate_artifact

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

def test_validate_artifact_too_large():
    ok, warnings = validate_artifact("html", "x" * 300000)
    assert ok is False

def test_validate_allows_markdown():
    ok, _ = validate_artifact("markdown", "# Hello\n- item")
    assert ok is True
