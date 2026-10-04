"""
Embedding service — local MiniLM (384d) primary, with Ollama/OpenAI fallback.
"""
import logging
from functools import lru_cache
from typing import List
import httpx
from app.config import settings

logger = logging.getLogger("lenny.embeddings")

@lru_cache(maxsize=1)
def _local_model():
    from sentence_transformers import SentenceTransformer
    logger.info(f"Loading local embedding model: {settings.embedding_model}")
    return SentenceTransformer(settings.embedding_model)

def embed_texts_sync(texts: List[str]) -> List[List[float]]:
    provider = settings.embedding_provider
    if provider == "local":
        model = _local_model()
        # normalize for cosine
        return model.encode(texts, normalize_embeddings=True, batch_size=settings.embed_batch_size).tolist()
    elif provider == "ollama":
        return _embed_ollama(texts)
    elif provider == "openai":
        return _embed_openai(texts)
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")

def embed_query_sync(text: str) -> List[float]:
    return embed_texts_sync([text])[0]

def _embed_ollama(texts: List[str]) -> List[List[float]]:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/embed"
    with httpx.Client(timeout=60) as client:
        r = client.post(url, json={"model": settings.ollama_embed_model, "input": texts})
        r.raise_for_status()
        j = r.json()
        # Batch input returns {"embeddings": [[...], ...]} positionally;
        # single-text servers may return {"embedding": [...]} instead.
        if "embeddings" in j:
            return [list(e) for e in j["embeddings"]]
        elif "embedding" in j:
            return [list(j["embedding"])]
        else:
            raise RuntimeError(f"Unexpected Ollama embed response keys: {sorted(j.keys())}")

def _embed_openai(texts: List[str]) -> List[List[float]]:
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.embeddings.create(model=settings.openai_embed_model, input=texts)
    return [d.embedding for d in resp.data]

# Async wrappers that run in threadpool (to avoid blocking event loop)
import asyncio

async def embed_texts(texts: List[str]) -> List[List[float]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, embed_texts_sync, texts)

async def embed_query(text: str) -> List[float]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, embed_query_sync, text)
