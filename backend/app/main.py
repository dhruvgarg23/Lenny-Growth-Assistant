import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.config import settings
from app.routes.health import router as health_router
from app.routes.sessions import router as sessions_router
from app.routes.chat import router as chat_router
from app.middleware.request_id import RequestIdMiddleware

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("lenny.api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Lenny Growth Assistant v{settings.app_version} — provider={settings.llm_provider} ollama={settings.ollama_model}")
    yield
    logger.info("Shutting down")

app = FastAPI(
    title="Lenny Growth Assistant",
    description="Grounded RAG over Lenny's Podcast transcripts — chat, Ship30 essays, artifacts.",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# Routes
app.include_router(health_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(chat_router, prefix="/api")

@app.get("/")
async def root():
    return {"service": "lenny-growth-assistant", "version": settings.app_version, "docs": "/docs"}

@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logger.exception(f"Unhandled: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "type": type(exc).__name__})

# For local `python -m app.main`
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
