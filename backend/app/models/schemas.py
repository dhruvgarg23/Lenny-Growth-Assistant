from typing import Optional, Literal, Any
from pydantic import BaseModel, Field

# ── Session ──
class SessionCreate(BaseModel):
    title: Optional[str] = Field(default="New chat", max_length=255)

class SessionOut(BaseModel):
    id: str
    title: str
    user_id: str
    created_at: str
    updated_at: str
    message_count: int = 0

# ── Messages ──
class SourceCite(BaseModel):
    document_id: str
    chunk_id: str
    source_path: str
    title: str
    guest: Optional[str] = None
    score: Optional[float] = None
    excerpt: Optional[str] = None

class MessageOut(BaseModel):
    id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceCite] = Field(default_factory=list)
    artifact: Optional[dict] = None
    meta: Optional[dict] = None
    created_at: str

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    mode: Literal["chat", "ship30", "artifact"] = "chat"
    # artifact sub-type
    artifact_type: Optional[Literal["markdown"]] = None

class ChatStreamEvent(BaseModel):
    event: str
    data: dict

# ── Health / Config ──
class HealthOut(BaseModel):
    status: str
    version: str
    provider: dict
    ollama_reachable: bool = False
    db_ok: bool = False
    active_sessions: int = 0

class ConfigOut(BaseModel):
    provider: dict
    retrieval: dict
    llm_models: dict

# ── Artifact ──
class ArtifactOut(BaseModel):
    type: Literal["markdown"]
    content: str
    title: Optional[str] = None
