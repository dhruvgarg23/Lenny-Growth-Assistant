import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.config import settings, runtime
from app.observability.logger import configure_logging, get_logger
from app.routes.health import router as health_router
from app.routes.sessions import router as sessions_router
from app.routes.chat import router as chat_router
from app.middleware.request_id import RequestIdMiddleware

# Configure structured logging
configure_logging(level=settings.log_level, json_logs=settings.log_json)
logger = get_logger("lenny.api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Lenny Growth Assistant v{settings.app_version} starting up",
        extra={
            "event": "app_startup",
            "version": settings.app_version,
            "provider": runtime.provider,
            "model": runtime.model,
            "embedding_model": settings.embedding_model,
            "log_level": settings.log_level,
        },
    )
    yield
    logger.info("Lenny Growth Assistant shutting down", extra={"event": "app_shutdown"})

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
    expose_headers=["X-Request-ID", "X-Response-Time"],
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
    request_id = getattr(request.state, "request_id", "-")
    logger.error(
        f"Unhandled exception: {exc}",
        extra={"event": "unhandled_exception", "error": str(exc), "request_id": request_id, "path": request.url.path},
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__, "request_id": request_id},
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
