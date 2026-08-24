"""
Hybrid retrieval — pgvector cosine + Postgres full-text (ts_rank) fused via RRF k=60.
"""
import logging
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.config import settings
from app.services.embeddings import embed_query

logger = logging.getLogger("lenny.retrieval")

RRF_K = 60

# Build the hybrid SQL — one round trip, tenant-free for now (single-tenant).
# Uses vector <=> cosine distance and tsvector @@ websearch_to_tsquery.
HYBRID_SQL = text("""
WITH query_emb AS (
  SELECT CAST(:qvec AS vector) AS emb
),
vector_hits AS (
  SELECT
    c.id,
    c.content,
    c.document_id,
    d.title,
    d.source_path,
    d.guest,
    1 - (c.embedding <=> (SELECT emb FROM query_emb)) AS vector_score,
    ROW_NUMBER() OVER (ORDER BY c.embedding <=> (SELECT emb FROM query_emb)) AS rnk
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE c.embedding IS NOT NULL
  ORDER BY c.embedding <=> (SELECT emb FROM query_emb)
  LIMIT :cand_k
),
keyword_hits AS (
  SELECT
    c.id,
    c.content,
    c.document_id,
    d.title,
    d.source_path,
    d.guest,
    ts_rank_cd(c.tsv, websearch_to_tsquery('english', :qtext)) AS text_score,
    ROW_NUMBER() OVER (ORDER BY ts_rank_cd(c.tsv, websearch_to_tsquery('english', :qtext)) DESC) AS rnk
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE c.tsv @@ websearch_to_tsquery('english', :qtext)
  ORDER BY text_score DESC
  LIMIT :cand_k
),
fused AS (
  SELECT id, SUM(score) AS rrf_score FROM (
    SELECT id, 1.0 / (:rrf_k + rnk) AS score FROM vector_hits
    UNION ALL
    SELECT id, 1.0 / (:rrf_k + rnk) AS score FROM keyword_hits
  ) u GROUP BY id
)
SELECT
  COALESCE(v.id, k.id) AS id,
  COALESCE(v.content, k.content) AS content,
  COALESCE(v.document_id, k.document_id) AS document_id,
  COALESCE(v.title, k.title) AS title,
  COALESCE(v.source_path, k.source_path) AS source_path,
  COALESCE(v.guest, k.guest) AS guest,
  COALESCE(v.vector_score, 0) AS vector_score,
  COALESCE(k.text_score, 0) AS text_score,
  f.rrf_score
FROM fused f
LEFT JOIN vector_hits v ON v.id = f.id
LEFT JOIN keyword_hits k ON k.id = f.id
ORDER BY f.rrf_score DESC
LIMIT :top_k;
""")

# Fallback vector-only (if keyword leg finds nothing)
VECTOR_ONLY_SQL = text("""
SELECT
  c.id,
  c.content,
  c.document_id,
  d.title,
  d.source_path,
  d.guest,
  1 - (c.embedding <=> CAST(:qvec AS vector)) AS vector_score,
  0::float AS text_score,
  1.0 / (:rrf_k + ROW_NUMBER() OVER (ORDER BY c.embedding <=> CAST(:qvec AS vector))) AS rrf_score
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE c.embedding IS NOT NULL
ORDER BY c.embedding <=> CAST(:qvec AS vector)
LIMIT :top_k;
""")

async def hybrid_search(db: AsyncSession, query: str, top_k: int | None = None, candidate_k: int | None = None) -> List[Dict[str, Any]]:
    if not query or not query.strip():
        return []
    top_k = top_k or settings.retrieval_k
    candidate_k = candidate_k or settings.candidate_k

    # Embed query (may be slow — do before DB tx holds connection)
    try:
        qvec = await embed_query(query)
    except Exception as e:
        logger.exception(f"Embedding failed: {e}")
        raise RuntimeError(f"Embedding failed: {e}") from e

    qvec_str = "[" + ",".join(f"{x:.6f}" for x in qvec) + "]"

    try:
        rows = (await db.execute(HYBRID_SQL, {"qvec": qvec_str, "qtext": query, "cand_k": candidate_k, "top_k": top_k, "rrf_k": RRF_K})).mappings().all()
        # If hybrid returned nothing (e.g., keyword leg empty and vector leg filtered?), fallback to vector-only
        if not rows:
            rows = (await db.execute(VECTOR_ONLY_SQL, {"qvec": qvec_str, "top_k": top_k, "rrf_k": RRF_K})).mappings().all()
        # Normalize to dicts
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "id": str(r["id"]),
                "content": r["content"],
                "document_id": str(r["document_id"]),
                "title": r["title"],
                "source_path": r["source_path"],
                "guest": r["guest"],
                "vector_score": float(r["vector_score"] or 0),
                "text_score": float(r["text_score"] or 0),
                "rrf_score": float(r["rrf_score"] or 0),
                "confidence": float(r["rrf_score"] or 0),  # alias for abstention gating
            })
        # Optional: filter by min confidence — but keep at least top 2 if we have them
        # We gate at chat layer, not here.
        return out
    except Exception as e:
        logger.exception(f"Hybrid search SQL failed: {e}")
        # Try vector-only as last resort
        try:
            rows = (await db.execute(VECTOR_ONLY_SQL, {"qvec": qvec_str, "top_k": top_k, "rrf_k": RRF_K})).mappings().all()
            return [
                {"id": str(r["id"]), "content": r["content"], "document_id": str(r["document_id"]), "title": r["title"], "source_path": r["source_path"], "guest": r["guest"], "vector_score": float(r["vector_score"] or 0), "text_score": 0.0, "rrf_score": float(r["rrf_score"] or 0), "confidence": float(r["rrf_score"] or 0)}
                for r in rows
            ]
        except Exception as e2:
            logger.exception(f"Vector-only fallback also failed: {e2}")
            raise
