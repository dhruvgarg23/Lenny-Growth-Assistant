"""
Artifact preparation — Markdown only.

Artifacts are Markdown documents extracted from the model reply (fenced
```markdown blocks preferred, raw text otherwise) and capped at
MAX_ARTIFACT_CHARS. There is no HTML artifact path: Markdown renders
through the client's Markdown renderer, so no HTML sanitization is needed.
"""
import re
from dataclasses import dataclass, field
from typing import Literal

from app.observability.logger import get_logger

logger = get_logger("lenny.artifacts")


@dataclass(frozen=True)
class PreparedArtifact:
    """Output of the artifact seam: safe to store and render, plus warnings."""

    type: Literal["markdown"]
    content: str
    warnings: list = field(default_factory=list)
    raw: str | None = None


MAX_ARTIFACT_CHARS = 200_000

_MD_FENCE_RE = re.compile(r"```markdown(.*?)```", flags=re.S | re.I)


def prepare_artifact(text: str, artifact_type: Literal["markdown"] = "markdown") -> tuple[str, PreparedArtifact]:
    """Single producing path: extract the markdown fence first, enforce the
    size cap. Returns (stored_content, artifact)."""
    m = _MD_FENCE_RE.search(text)
    raw = m.group(1).strip() if m else text
    content, warnings = raw, []

    if len(content) > MAX_ARTIFACT_CHARS:
        content = content[:MAX_ARTIFACT_CHARS]
        warnings.append(f"Artifact truncated to {MAX_ARTIFACT_CHARS} chars.")
        logger.warning("artifact_truncated_size", extra={"event": "artifact_validation_error", "size": len(text)})

    artifact = PreparedArtifact(
        type=artifact_type,
        content=content,
        warnings=warnings,
        raw=None,
    )
    return content, artifact
