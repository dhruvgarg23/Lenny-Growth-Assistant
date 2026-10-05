"""
Lightweight intent router — keyword + LLM fallback later.
Determines mode: chat | ship30 | artifact
"""
import re

SHIP30_TRIGGERS = [
    r"ship\s*30", r"atomic essay", r"essay", r"1,?250\s*words", r"ship30"
]
ARTIFACT_TRIGGERS = [
    r"artifact", r"render", r"html\/css", r"markdown doc", r"one-?pager", r"memo", r"canvas"
]

def route_intent(message: str, requested_mode: str | None = None) -> str:
    if requested_mode in ("chat", "ship30", "artifact"):
        return requested_mode
    low = message.lower()
    for pat in SHIP30_TRIGGERS:
        if re.search(pat, low):
            return "ship30"
    for pat in ARTIFACT_TRIGGERS:
        if re.search(pat, low):
            return "artifact"
    return "chat"

def detect_artifact_type(message: str, explicit: str | None = None) -> str:
    # Markdown-only artifacts; the explicit/keyword hints are accepted but ignored.
    return "markdown"
