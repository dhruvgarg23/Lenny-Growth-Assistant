"""
Anthropic Claude Agent SDK — Tool Schemas and Tool Handlers.
Defines agent tools for transcript retrieval, Ship 30 essay formatting, and artifact generation.
"""
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval import hybrid_search
from app.services.artifacts import sanitize_html

ANTHROPIC_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "search_transcripts",
        "description": "Search Lenny's Podcast & Newsletter transcripts for product management, growth, onboarding, pricing, retention, and leadership insights using hybrid vector + lexical search.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query or concept to find in the podcast archives."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "apply_ship30_skill",
        "description": "Invokes the Ship 30 for 30 content creation skill to format findings into a ~1,250-word atomic essay with high-voltage headline, 1/3/1 cadence, bold subheads, bulleted frameworks, and grounded citations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The product management or growth topic to write the Ship 30 essay about."
                }
            },
            "required": ["topic"]
        }
    },
    {
        "name": "render_artifact",
        "description": "Creates an interactive HTML/CSS or Markdown artifact (e.g. comparison table, launch checklist, strategy memo, one-pager) to be displayed in the split-pane artifact viewer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artifact_type": {
                    "type": "string",
                    "enum": ["html", "markdown"],
                    "description": "The markup format for the artifact."
                },
                "title": {
                    "type": "string",
                    "description": "Title of the artifact."
                },
                "content": {
                    "type": "string",
                    "description": "The self-contained HTML/CSS code or Markdown text for the artifact."
                }
            },
            "required": ["artifact_type", "title", "content"]
        }
    }
]


async def execute_tool(
    name: str,
    tool_input: Dict[str, Any],
    db: AsyncSession
) -> Dict[str, Any]:
    """Execute the requested tool and return a structured result."""
    if name == "search_transcripts":
        query = tool_input.get("query", "")
        results = await hybrid_search(db, query)
        sources = [
            {
                "document_id": r["document_id"],
                "chunk_id": r["id"],
                "source_path": r["source_path"],
                "title": r["title"],
                "guest": r["guest"],
                "score": r["rrf_score"],
                "excerpt": r["content"][:300]
            }
            for r in results
        ]
        return {
            "count": len(results),
            "top_confidence": results[0]["rrf_score"] if results else 0.0,
            "sources": sources,
            "raw_contexts": results
        }

    elif name == "render_artifact":
        art_type = tool_input.get("artifact_type", "html")
        title = tool_input.get("title", "Generated Artifact")
        content = tool_input.get("content", "")
        warnings = []
        if art_type == "html":
            sanitized, warnings = sanitize_html(content)
            content = sanitized
        return {
            "type": art_type,
            "title": title,
            "content": content,
            "warnings": warnings,
            "rendered": True
        }

    elif name == "apply_ship30_skill":
        topic = tool_input.get("topic", "")
        return {
            "skill": "ship30",
            "topic": topic,
            "rules": [
                "Target ~1,250 words",
                "High-voltage headline with PM niche hook",
                "1/3/1 sentence rhythm",
                "3-5 bold ### sections with bullets and selective bold",
                "Clear CTA & takeaway",
                "Direct transcript citations [source: path]"
            ]
        }

    raise ValueError(f"Unknown tool: {name}")
