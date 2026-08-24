"""
Lenny Growth Assistant — Centralized configuration.
All settings via env / .env. Provider toggle is explicit and validated.
"""
import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings
from pydantic import Field

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # ── App ──
    app_name: str = "Lenny Growth Assistant"
    app_version: str = "1.0.0"
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    debug: bool = False

    # ── Provider Toggle ──
    llm_provider: Literal["ollama", "anthropic", "openai", "openrouter"] = Field(
        default="ollama", alias="LLM_PROVIDER"
    )
    ollama_base_url: str = Field(
        default="http://host.docker.internal:11434", alias="OLLAMA_BASE_URL"
    )
    ollama_model: str = Field(default="llama3.1:8b", alias="OLLAMA_MODEL")
    ollama_embed_model: str = Field(
        default="nomic-embed-text", alias="OLLAMA_EMBED_MODEL"
    )

    # Cloud (optional)
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-sonnet-4-20250514", alias="ANTHROPIC_MODEL"
    )
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_embed_model: str = Field(
        default="text-embedding-3-small", alias="OPENAI_EMBED_MODEL"
    )
    # OpenRouter — OpenAI-compatible (use stealth/ox-alpha for testing)
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="stealth/ox-alpha", alias="OPENROUTER_MODEL"
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_referer: str = Field(default="", alias="OPENROUTER_REFERER")
    openrouter_app_title: str = Field(default="Lenny Growth Assistant", alias="OPENROUTER_APP_TITLE")

    # ── Embeddings ──
    embedding_provider: Literal["local", "ollama", "openai"] = Field(
        default="local", alias="EMBEDDING_PROVIDER"
    )
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2", alias="EMBEDDING_MODEL"
    )
    vector_dim: int = Field(default=384, alias="VECTOR_DIM")
    embed_batch_size: int = Field(default=32, alias="EMBED_BATCH_SIZE")

    # ── Retrieval ──
    chunk_size: int = Field(default=800, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=100, alias="CHUNK_OVERLAP")
    retrieval_k: int = Field(default=8, alias="RETRIEVAL_K")
    candidate_k: int = Field(default=30, alias="CANDIDATE_K")
    rag_min_confidence: float = Field(default=0.01, alias="RAG_MIN_CONFIDENCE")
    rrf_k: int = 60

    # ── DB ──
    database_url: str = Field(
        default="postgresql+asyncpg://lenny:lenny@localhost:5432/lenny_growth",
        alias="DATABASE_URL",
    )

    # ── CORS / Rate Limit ──
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:80,http://localhost",
        alias="CORS_ORIGINS",
    )
    chat_rate_limit: str = "20/minute"
    ingest_rate_limit: str = "5/minute"

    # ── Paths ──
    data_dir: Path = Field(default=_BACKEND_DIR / "data")
    source_dir: Path = Field(default=_BACKEND_DIR / "data" / "source")

    model_config = {
        "env_file": str(_BACKEND_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "case_sensitive": False,
    }

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_cloud_configured(self) -> bool:
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        if self.llm_provider == "openrouter":
            return bool(self.openrouter_api_key)
        return True  # ollama needs no key

    def provider_status(self) -> dict:
        return {
            "selected": self.llm_provider,
            "ollama_model": self.ollama_model,
            "ollama_base_url": self.ollama_base_url,
            "anthropic_configured": bool(self.anthropic_api_key),
            "openai_configured": bool(self.openai_api_key),
            "openrouter_configured": bool(self.openrouter_api_key),
            "openrouter_model": self.openrouter_model,
            "openrouter_base_url": self.openrouter_base_url,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "vector_dim": self.vector_dim,
        }


settings = Settings()
