"""LLM provider seam — facade over per-provider adapters."""
from app.services.llm.facade import check_available, stream

__all__ = ["check_available", "stream"]
