from fastapi import APIRouter
from sqlalchemy import text
from app.config import settings
from app.services.database import engine
from app.services.llm import ollama_health
from sqlalchemy.ext.asyncio import AsyncSession
import logging

router = APIRouter()
logger = logging.getLogger("lenny.health")

@router.get("/health")
async def health():
    db_ok = True
    active_sessions = 0
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        # count sessions
        async with engine.connect() as conn:
            r = await conn.execute(text("SELECT COUNT(*) FROM sessions"))
            active_sessions = r.scalar() or 0
    except Exception as e:
        logger.warning(f"DB health failed: {e}")
        db_ok = False

    ollama_ok = False
    if settings.llm_provider == "ollama":
        ollama_ok = await ollama_health()

    return {
        "status": "healthy" if db_ok else "degraded",
        "version": settings.app_version,
        "provider": settings.provider_status(),
        "ollama_reachable": ollama_ok,
        "db_ok": db_ok,
        "active_sessions": active_sessions,
    }

@router.get("/config")
async def get_config():
    return {
        "provider": settings.provider_status(),
        "retrieval": {
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "retrieval_k": settings.retrieval_k,
            "candidate_k": settings.candidate_k,
            "rag_min_confidence": settings.rag_min_confidence,
            "rrf_k": settings.rrf_k,
        },
        "llm_models": {
            "ollama": settings.ollama_model,
            "anthropic": settings.anthropic_model,
            "openai": settings.openai_model,
            "openrouter": settings.openrouter_model,
        },
    }
