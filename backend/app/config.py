"""
Lenny Growth Assistant — Centralized configuration.
All settings via env / .env. Provider toggle is explicit and validated.
Toggle: ollama (local) | groq (cloud). No auto-fallback.
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
    log_json: bool = Field(default=False, alias="LOG_JSON")
    debug: bool = False

    # ── Provider Toggle ──
    # Options: ollama | groq | anthropic
    # ollama    = local (llama3.1:8b via host.docker.internal:11434)
    # anthropic = cloud (Anthropic Claude Agent SDK / AsyncAnthropic) — models: claude-3-5-sonnet-20241022, claude-3-5-haiku-20241022, claude-3-opus-20240229
    # groq      = cloud (https://api.groq.com/openai/v1) — models: llama-3.3-70b-versatile, openai/gpt-oss-120b, llama-3.1-8b-instant
    # Fallback: no auto-switch. If selected provider fails → API returns SSE error / 503; change LLM_PROVIDER and restart.
    llm_provider: Literal["ollama", "groq", "anthropic"] = Field(
        default="ollama", alias="LLM_PROVIDER"
    )
    ollama_base_url: str = Field(
        default="http://host.docker.internal:11434", alias="OLLAMA_BASE_URL"
    )
    ollama_model: str = Field(default="llama3.1:8b", alias="OLLAMA_MODEL")
    ollama_embed_model: str = Field(
        default="nomic-embed-text", alias="OLLAMA_EMBED_MODEL"
    )

    # Anthropic — Claude Agent SDK / Messages API
    # Get key: https://console.anthropic.com/ → ANTHROPIC_API_KEY
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022", alias="ANTHROPIC_MODEL"
    )
    anthropic_base_url: str = Field(
        default="https://api.anthropic.com", alias="ANTHROPIC_BASE_URL"
    )
    anthropic_models: str = Field(
        default="claude-3-5-sonnet-20241022,claude-3-5-haiku-20241022,claude-3-opus-20240229",
        alias="ANTHROPIC_MODELS",
    )

    # Groq — OpenAI-compatible (https://api.groq.com/openai/v1)
    # Get key: https://console.groq.com/keys → GROQ_API_KEY
    # Models: llama-3.3-70b-versatile (default, 280t/s 131k), openai/gpt-oss-120b (500t/s reasoning), llama-3.1-8b-instant (560t/s), qwen/qwen3-32b (reasoning, hidden)
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(
        default="llama-3.3-70b-versatile", alias="GROQ_MODEL"
    )
    groq_base_url: str = Field(
        default="https://api.groq.com/openai/v1", alias="GROQ_BASE_URL"
    )
    # Allowlist for UI visibility (env-only toggle, restart required per model switch)
    groq_models: str = Field(
        default="llama-3.3-70b-versatile,openai/gpt-oss-120b,llama-3.1-8b-instant,qwen/qwen3-32b",
        alias="GROQ_MODELS",
    )
    ollama_models: str = Field(default="llama3.1:8b", alias="OLLAMA_MODELS")

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
    def groq_models_list(self) -> list[str]:
        return [m.strip() for m in self.groq_models.split(",") if m.strip()]

    @property
    def anthropic_models_list(self) -> list[str]:
        return [m.strip() for m in self.anthropic_models.split(",") if m.strip()]

    @property
    def ollama_models_list(self) -> list[str]:
        return [m.strip() for m in self.ollama_models.split(",") if m.strip()]

    @property
    def selected_model(self) -> str:
        if self.llm_provider == "anthropic":
            return self.anthropic_model
        elif self.llm_provider == "groq":
            return self.groq_model
        return self.ollama_model

    @property
    def is_cloud_configured(self) -> bool:
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        elif self.llm_provider == "groq":
            return bool(self.groq_api_key)
        return True  # ollama needs no key

    def provider_status(self) -> dict:
        return {
            "selected": self.llm_provider,
            "selected_model": self.selected_model,
            "ollama_model": self.ollama_model,
            "ollama_base_url": self.ollama_base_url,
            "ollama_models": self.ollama_models_list,
            "anthropic_configured": bool(self.anthropic_api_key),
            "anthropic_model": self.anthropic_model,
            "anthropic_models": self.anthropic_models_list,
            "groq_configured": bool(self.groq_api_key),
            "groq_model": self.groq_model,
            "groq_base_url": self.groq_base_url,
            "groq_models": self.groq_models_list,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "vector_dim": self.vector_dim,
        }


settings = Settings()


class RuntimeConfig:
    """Mutable runtime state for provider/model switching.
    Initialized from Settings but can be updated at runtime via API
    without restarting the container. Resets to .env defaults on restart."""

    def __init__(self, s: Settings):
        self._settings = s
        self.provider: str = s.llm_provider
        self.model: str = s.selected_model

    @property
    def is_anthropic(self) -> bool:
        return self.provider == "anthropic"

    @property
    def is_groq(self) -> bool:
        return self.provider == "groq"

    @property
    def anthropic_api_key(self) -> str:
        return self._settings.anthropic_api_key

    @property
    def anthropic_base_url(self) -> str:
        return self._settings.anthropic_base_url

    @property
    def groq_api_key(self) -> str:
        return self._settings.groq_api_key

    @property
    def groq_base_url(self) -> str:
        return self._settings.groq_base_url

    @property
    def ollama_base_url(self) -> str:
        return self._settings.ollama_base_url

    def allowed_models(self, provider: str) -> list[str]:
        if provider == "anthropic":
            return self._settings.anthropic_models_list
        elif provider == "groq":
            return self._settings.groq_models_list
        return self._settings.ollama_models_list

    def switch(self, provider: str, model: str) -> dict:
        """Switch provider and model at runtime. Returns new status."""
        allowed = self.allowed_models(provider)
        if model not in allowed:
            raise ValueError(
                f"Model '{model}' not in allowed list for {provider}: {allowed}"
            )
        if provider == "anthropic" and not self._settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        if provider == "groq" and not self._settings.groq_api_key:
            raise ValueError("GROQ_API_KEY not configured")
        self.provider = provider
        self.model = model
        return self.status()

    def status(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "allowed_models": {
                "ollama": self._settings.ollama_models_list,
                "anthropic": self._settings.anthropic_models_list,
                "groq": self._settings.groq_models_list,
            },
            "anthropic_configured": bool(self._settings.anthropic_api_key),
            "groq_configured": bool(self._settings.groq_api_key),
        }


runtime = RuntimeConfig(settings)
