"""
Anthropic Claude Agent SDK Runner.
Implements the autonomous agent loop with Anthropic Tool Calling,
Skills orchestration (Ship 30 for 30), and split-pane Artifact generation.
"""
import time
from typing import AsyncGenerator, Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import anthropic

from app.config import runtime, settings
from app.agent.tools import ANTHROPIC_TOOLS, execute_tool
from app.services.retrieval import hybrid_search
from app.services.prompts import (
    build_grounded_messages,
    build_ship30_messages,
    build_artifact_messages,
)
from app.services.artifacts import sanitize_html
from app.observability.logger import get_logger, Timer

logger = get_logger("lenny.agent.claude")


class ClaudeAgent:
    """Agent runtime built on Anthropic Claude Agent SDK / AsyncAnthropic."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or runtime.anthropic_api_key
        self.model = model or runtime.model
        self.base_url = runtime.anthropic_base_url

    def _client(self) -> anthropic.AsyncAnthropic:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured.")
        return anthropic.AsyncAnthropic(api_key=self.api_key, base_url=self.base_url)

    async def execute_agent_loop(
        self,
        query: str,
        history: List[Dict[str, str]],
        db: AsyncSession,
        mode: str = "chat",
        artifact_type: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executes the agent workflow:
        1. Emits retrieving status and executes hybrid search.
        2. Checks confidence threshold and handles abstention.
        3. Formulates prompt with knowledge context & active skill.
        4. Streams response tokens directly from Claude using Anthropic SDK.
        5. Emits structured artifact and done payloads.
        """
        yield {"event": "status", "data": {"stage": "retrieving", "message": "Searching Lenny transcripts with Claude Agent…"}}

        with Timer() as ret_timer:
            try:
                contexts = await hybrid_search(db, query)
            except Exception as e:
                logger.exception(f"Agent retrieval failed: {e}")
                contexts = []

        top_conf = contexts[0]["rrf_score"] if contexts else 0.0
        if not contexts or top_conf < settings.rag_min_confidence:
            yield {"event": "sources", "data": {"sources": [], "confidence": top_conf, "abstained": True}}
            abstain_msg = (
                "I don't have support in the available Lenny transcripts for that. "
                "Try asking about product management, onboarding, PLG, pricing, or retention."
            )
            yield {"event": "token", "data": {"delta": abstain_msg}}
            yield {
                "event": "done",
                "data": {
                    "sources": [],
                    "abstained": True,
                    "confidence": top_conf,
                    "agent": "Anthropic Claude Agent SDK",
                },
            }
            return

        sources = [
            {
                "document_id": c["document_id"],
                "chunk_id": c["id"],
                "source_path": c["source_path"],
                "title": c["title"],
                "guest": c["guest"],
                "score": c["rrf_score"],
                "excerpt": c["content"][:280],
            }
            for c in contexts
        ]
        yield {"event": "sources", "data": {"sources": sources, "confidence": top_conf}}
        yield {"event": "status", "data": {"stage": "generating", "message": "Generating response with Claude…"}}

        # Build prompt messages depending on skill mode
        if mode == "ship30":
            messages = build_ship30_messages(query, history, contexts)
        elif mode == "artifact":
            messages = build_artifact_messages(query, history, contexts, artifact_type or "html")
        else:
            messages = build_grounded_messages(query, history, contexts)

        # Extract system prompt vs user/assistant conversation for Anthropic SDK
        systems = []
        convo = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                systems.append(content)
            elif role in ("user", "assistant"):
                if convo and convo[-1]["role"] == role:
                    convo[-1]["content"] += "\n\n" + content
                else:
                    convo.append({"role": role, "content": content})
        if not convo:
            convo = [{"role": "user", "content": query}]

        system_prompt = "\n\n".join(systems)

        client = self._client()
        full_content = ""
        try:
            async with client.messages.stream(
                model=self.model,
                system=system_prompt if system_prompt else None,
                messages=convo,
                temperature=0.2,
                max_tokens=4096,
            ) as stream:
                async for text in stream.text_stream:
                    if text:
                        full_content += text
                        yield {"event": "token", "data": {"delta": text}}
        except Exception as exc:
            logger.error(f"Claude agent streaming failed: {exc}", exc_info=True)
            yield {"event": "error", "data": {"detail": str(exc), "agent": "Anthropic Claude Agent SDK"}}
            return

        artifact = None
        if mode == "artifact":
            raw = full_content
            if artifact_type == "html":
                import re
                m = re.search(r"```html(.*?)```", raw, flags=re.S | re.I)
                if m:
                    raw = m.group(1)
                sanitized, warnings = sanitize_html(raw)
                artifact = {"type": "html", "content": sanitized, "raw": raw[:200000], "warnings": warnings}
                yield {"event": "artifact", "data": {"artifact": artifact}}
            else:
                import re
                m = re.search(r"```markdown(.*?)```", raw, flags=re.S | re.I)
                if m:
                    raw = m.group(1).strip()
                artifact = {"type": "markdown", "content": raw, "warnings": []}
                yield {"event": "artifact", "data": {"artifact": artifact}}

        yield {
            "event": "done",
            "data": {
                "sources": sources,
                "confidence": top_conf,
                "mode": mode,
                "artifact": artifact,
                "agent": "Anthropic Claude Agent SDK",
            },
        }
