from app.services.artifacts import prepare_artifact, MAX_ARTIFACT_CHARS

def test_prepare_markdown_passes_through_with_fence_stripped():
    content, artifact = prepare_artifact("```markdown\n# Hello\n- item\n```", "markdown")
    assert content == "# Hello\n- item"
    assert artifact.type == "markdown" and artifact.raw is None

def test_prepare_markdown_without_fence_passes_through():
    content, artifact = prepare_artifact("# Hello\n- item", "markdown")
    assert content == "# Hello\n- item"
    assert artifact.type == "markdown"

def test_prepare_truncates_oversize_with_warning():
    content, artifact = prepare_artifact("x" * (MAX_ARTIFACT_CHARS + 100), "markdown")
    assert len(content) == MAX_ARTIFACT_CHARS
    assert any("truncated" in w for w in artifact.warnings)

def test_prepare_defaults_to_markdown():
    content, artifact = prepare_artifact("# Hello")
    assert artifact.type == "markdown"
    assert content == "# Hello"
