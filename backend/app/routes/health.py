from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.config import settings, runtime
from app.services.database import check_db_health
from app.services.llm.ollama import ollama_health
from app.observability.logger import get_logger, Timer

router = APIRouter()
logger = get_logger("lenny.health")

@router.get("/health")
async def health():
    db_stat = await check_db_health()
    db_ok = db_stat.get("ok", False)

    ollama_ok = False
    if runtime.provider == "ollama":
        ollama_ok = await ollama_health(runtime.ollama_base_url)

    return {
        "status": "healthy" if db_ok else "degraded",
        "version": settings.app_version,
        "provider": settings.provider_status(),
        "runtime": runtime.status(),
        "ollama_reachable": ollama_ok,
        "db_ok": db_ok,
        "active_sessions": db_stat.get("sessions_count", 0),
        "db_latency_ms": db_stat.get("latency_ms", 0),
    }

@router.get("/diagnostics")
async def diagnostics():
    """Detailed diagnostics probe across database, vector store, and model providers."""
    with Timer() as total_timer:
        db_stat = await check_db_health()

        ollama_stat = {"configured": bool(runtime.ollama_base_url)}
        if runtime.provider == "ollama":
            with Timer() as ot:
                reachable = await ollama_health(runtime.ollama_base_url)
            ollama_stat["reachable"] = reachable
            ollama_stat["latency_ms"] = ot.elapsed_ms

        groq_stat = {
            "configured": bool(runtime.groq_api_key),
            "base_url": runtime.groq_base_url,
            "selected_model": runtime.model if runtime.is_groq else None,
        }

    return {
        "status": "healthy" if db_stat.get("ok") else "degraded",
        "version": settings.app_version,
        "runtime": runtime.status(),
        "diagnostics": {
            "database": db_stat,
            "ollama": ollama_stat,
            "groq": groq_stat,
            "total_probe_duration_ms": total_timer.elapsed_ms,
        },
    }

@router.get("/config")
async def get_config():
    return {
        "provider": settings.provider_status(),
        "runtime": runtime.status(),
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
            "groq": settings.groq_model,
        },
        "allowed_models": {
            "ollama": settings.ollama_models_list,
            "groq": settings.groq_models_list,
        },
    }

class ModelSwitch(BaseModel):
    provider: str
    model: str

@router.put("/config/model")
async def switch_model(body: ModelSwitch):
    """Switch active LLM provider and model at runtime (no restart needed)."""
    if body.provider not in ("ollama", "groq"):
        raise HTTPException(status_code=400, detail=f"Unknown provider: {body.provider}. Use 'ollama' or 'groq'.")
    try:
        result = runtime.switch(body.provider, body.model)
        logger.info(f"Model switched → {body.provider}/{body.model}", extra={"event": "model_switched", "provider": body.provider, "model": body.model})
        return result
    except ValueError as e:
        logger.warning(f"Model switch rejected: {e}", extra={"event": "model_switch_rejected", "error": str(e)})
        raise HTTPException(status_code=400, detail=str(e))
