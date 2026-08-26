"""
Artifact sanitization — treat HTML as untrusted.

Permits: basic formatting, headings, lists, tables, inline SVG-free images, <style> with safe CSS.
Blocks: scripts, event handlers, iframes, forms, objects, embeds, external fetch via meta.

Observability additions:
  - Structured logging on artifact sanitization (raw length, output length, duration_ms).
  - Warnings and blocked pattern logs for diagnosis of rendering failures.
"""
import re
from typing import Literal

from app.observability.logger import get_logger, Timer

logger = get_logger("lenny.artifacts")

try:
    import bleach
    from bleach.css_sanitizer import CSSSanitizer
except Exception:
    bleach = None  # fallback to regex

# Allowed HTML tags for artifacts
ALLOWED_TAGS = [
    "h1","h2","h3","h4","h5","h6","p","br","hr","ul","ol","li",
    "strong","em","b","i","u","a","blockquote","code","pre","span","div","section","article",
    "header","footer","main","table","thead","tbody","tr","th","td","caption","colgroup","col",
    "figure","figcaption","small","sup","sub","mark","kbd","details","summary","style"
]
ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "span": ["class"],
    "div": ["class"],
    "section": ["class"],
    "article": ["class"],
    "table": ["class"],
    "th": ["colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
    "code": ["class"],
    "pre": ["class"],
}

# Very small CSS allowlist (bleach's CSSSanitizer handles)
ALLOWED_CSS = [
    "color","background","background-color","font-size","font-weight","font-family",
    "text-align","margin","margin-top","margin-bottom","margin-left","margin-right",
    "padding","padding-top","padding-bottom","padding-left","padding-right",
    "border","border-radius","border-color","border-width","border-style",
    "display","gap","grid-template-columns","flex","flex-direction","line-height",
    "max-width","width","height","box-shadow","opacity","letter-spacing"
]

FORBIDDEN_PATTERNS = [
    re.compile(r"<script", re.I),
    re.compile(r"<iframe", re.I),
    re.compile(r"<object", re.I),
    re.compile(r"<embed", re.I),
    re.compile(r"<form", re.I),
    re.compile(r"on\w+\s*=", re.I),  # on* handlers
    re.compile(r"javascript:", re.I),
    re.compile(r"@import", re.I),
    re.compile(r"url\s*\(", re.I),  # block url() to prevent exfil
    re.compile(r"position\s*:\s*fixed", re.I),
    re.compile(r"<meta[^>]*http-equiv", re.I),
]

def sanitize_html(raw: str) -> tuple[str, list[str]]:
    with Timer() as t:
        warnings: list[str] = []
        # Pre-check forbidden patterns
        for pat in FORBIDDEN_PATTERNS:
            if pat.search(raw):
                warnings.append(f"Blocked pattern: {pat.pattern}")

        if bleach is None:
            # minimal fallback — strip scripts
            cleaned = re.sub(r"<script.*?</script>", "", raw, flags=re.I|re.S)
            logger.warning("bleach_not_available_fallback_to_regex", extra={"event": "artifact_sanitize_fallback"})
            return cleaned, warnings

        # Extract <style> blocks and sanitize separately, keep them if safe
        style_blocks = re.findall(r"<style[^>]*>(.*?)</style>", raw, flags=re.I|re.S)
        safe_styles = []
        for block in style_blocks:
            b = block
            blocked = False
            for pat in FORBIDDEN_PATTERNS:
                if pat.search(b):
                    warnings.append(f"Blocked style pattern: {pat.pattern}")
                    blocked = True
                    break
            if not blocked:
                safe_styles.append(f"<style>{b}</style>")

        # Remove original style blocks for bleach pass
        no_style = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.I|re.S)

        css_sanitizer = CSSSanitizer(allowed_css_properties=ALLOWED_CSS) if bleach else None
        cleaned = bleach.clean(
            no_style,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRS,
            css_sanitizer=css_sanitizer,
            strip=True,
        )
        # Re-inject safe styles at top
        if safe_styles:
            cleaned = "\n".join(safe_styles) + "\n" + cleaned

        # Force links to noopener
        cleaned = cleaned.replace('target="_blank"', 'target="_blank" rel="noopener noreferrer"')
        
        logger.info(
            f"artifact_html_sanitized raw_len={len(raw)} clean_len={len(cleaned)} warnings={len(warnings)}",
            extra={
                "event": "artifact_sanitize_done",
                "raw_chars": len(raw),
                "clean_chars": len(cleaned),
                "warnings_count": len(warnings),
                "warnings": warnings[:5],
                "duration_ms": t.elapsed_ms,
            },
        )
        return cleaned, warnings

def sanitize_markdown(md: str) -> str:
    return md

def validate_artifact(artifact_type: Literal["markdown", "html"], content: str) -> tuple[bool, list[str]]:
    warnings: list[str] = []
    if artifact_type == "html":
        _, w = sanitize_html(content)
        warnings.extend(w)
    # Enforce size limits
    if len(content) > 200_000:
        msg = "Artifact too large (>200k chars), truncate."
        warnings.append(msg)
        logger.warning("artifact_validation_failed_size", extra={"event": "artifact_validation_error", "reason": msg, "size": len(content)})
        return False, warnings
    # Hard block if contains script even after sanitize attempt
    if re.search(r"<script|javascript:", content, flags=re.I):
        msg = "Contains disallowed script content."
        warnings.append(msg)
        logger.warning("artifact_validation_failed_script", extra={"event": "artifact_validation_error", "reason": msg})
        return False, warnings
    return True, warnings
