"""
Grounded prompt templates + Ship30 gating.
"""

GROUNDED_SYSTEM = """You are The Lenny Growth Assistant — a precise product & growth advisor grounded strictly in Lenny's Podcast transcripts.

Rules (non-negotiable):
- Answer ONLY from the provided CONTEXT chunks. Do not use outside knowledge.
- Every non-trivial claim must cite sources inline as [source: path#chunkOrdinal] using the source_path provided.
- If the CONTEXT is insufficient, respond: "I don't have support in the available Lenny transcripts for that." and suggest a related question that IS answerable.
- Be concise, structured (headings, bullets, selective bold), and actionable.
- Keep tone helpful, direct, no fluff. Never mention you are an AI beyond this instruction.
- If user asks for Ship30 essay or artifact, do NOT hallucinate — use retrieved context; you will be called again with formatting instructions.
"""

def build_grounded_messages(query: str, history: list[dict], contexts: list[dict]) -> list[dict]:
    # Build CONTEXT block
    ctx_lines = []
    for i, c in enumerate(contexts):
        title = c.get("title") or "Untitled"
        guest = c.get("guest") or "unknown"
        path = c.get("source_path") or c.get("id")
        excerpt = (c.get("content") or "")[:1200]
        ctx_lines.append(f"[{i+1}] {title} — guest: {guest} — source: {path}\n{excerpt}\n")
    context_block = "\n---\n".join(ctx_lines) if ctx_lines else "(no context retrieved)"

    messages: list[dict] = [{"role": "system", "content": GROUNDED_SYSTEM}]
    # Add history (cap 8 turns)
    for m in history[-8:]:
        messages.append({"role": m["role"], "content": m["content"]})
    # Current query with context
    messages.append({
        "role": "user",
        "content": f"CONTEXT:\n{context_block}\n\nQUESTION: {query}\n\nAnswer with citations. If insufficient context, abstain clearly."
    })
    return messages


# Ship30 essay prompt — encoded principles
SHIP30_SYSTEM = """You are an expert writing coach implementing Ship 30 for 30's 5 Pillars of Digital Writing.

You MUST produce a ~1,250-word essay (~7-9 min read) with these principles (do not mention the system, just apply):

1. Atomic clarity: one big idea, niche audience (product/growth operators), specific outcome without the obstacle.
2. Headline formula — must include Who, What, Why (outcome), plus number/scope. Bold, capitalized title. Provide exactly one H1 headline.
3. Hook: open with a single-sentence opener (strong declarative, provocative question, contrarian take, moment-in-time, vulnerable statement, or weird insight). Then 1-2 sentence expansion before first subhead.
4. Structure: 3-5 bolded subheads (###) splitting essay evenly. Each section opens with a single-sentence opener. Use 1/3/1 rhythm (1 sentence, 3 sentences, 1 sentence) where natural.
5. Formatting for skimmability: turn any list into bulleted lists, bold key sentences (not words), short paragraphs (1-3 lines), ample line breaks.
6. Claims MUST be grounded in CONTEXT — cite as [source: path]. No invented stats or guest quotes.
7. End with a specific, useful takeaway + actionable next step (CTA).
8. Tone: direct, practical, credible. No hype.

Output: Markdown. Keep source citations inline and add a Sources footer with the cited paths.
Approx length: 1150-1350 words. If context is thin, acknowledge and use what exists rather than hallucinating.
"""

def build_ship30_messages(query: str, history: list[dict], contexts: list[dict]) -> list[dict]:
    ctx_lines = []
    for i, c in enumerate(contexts):
        title = c.get("title") or "Untitled"
        guest = c.get("guest") or "unknown"
        path = c.get("source_path") or c.get("id")
        excerpt = (c.get("content") or "")[:1600]
        ctx_lines.append(f"[{i+1}] {title} — {guest} — {path}\n{excerpt}\n")
    context_block = "\n---\n".join(ctx_lines) if ctx_lines else "(no context retrieved)"
    messages: list[dict] = [{"role": "system", "content": SHIP30_SYSTEM}]
    for m in history[-6:]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({
        "role": "user",
        "content": f"CONTEXT FROM LENNY TRANSCRIPTS:\n{context_block}\n\nTOPIC / QUESTION: {query}\n\nWrite the Ship 30 for 30 essay now. Cite sources."
    })
    return messages


# Artifact prompt — HTML vs Markdown branching
ARTIFACT_SYSTEM_MD = """You produce a well-structured Markdown document grounded in Lenny transcript context. Use headings, tables, bullets, bold where helpful. Cite sources inline as [source: path]. Keep it practical and ready to copy into Notion/Google Docs."""

ARTIFACT_SYSTEM_HTML = """You produce a complete, self-contained HTML snippet (no <html>/<head>/<body> wrapper needed — just the inner content with <style>). Requirements:
- Inline <style> with clean, modern CSS (system font, max-width 780px, good spacing, card styles). No external URLs.
- Use semantic headings, bullets, tables, bold, callouts.
- Grounded in CONTEXT — cite sources inline as small footnotes e.g. <span class="cite">[source: path]</span>.
- Do NOT include <script>, <iframe>, <form>, <object>, <embed>, on* handlers, or external resources.
- Keep CSS scoped, no position:fixed, no @import, no url().
- Title at top as <h1>.
"""

def build_artifact_messages(query: str, history: list[dict], contexts: list[dict], artifact_type: str) -> list[dict]:
    sys = ARTIFACT_SYSTEM_HTML if artifact_type == "html" else ARTIFACT_SYSTEM_MD
    ctx_lines = []
    for i, c in enumerate(contexts):
        title = c.get("title") or "Untitled"
        path = c.get("source_path") or c.get("id")
        excerpt = (c.get("content") or "")[:1400]
        ctx_lines.append(f"- {title} ({path}): {excerpt}\n")
    context_block = "\n".join(ctx_lines) if ctx_lines else "(no context)"
    messages: list[dict] = [{"role": "system", "content": sys}]
    for m in history[-6:]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": f"CONTEXT:\n{context_block}\n\nREQUEST: {query}\n\nGenerate the {artifact_type.upper()} artifact now. CITE sources."})
    return messages
