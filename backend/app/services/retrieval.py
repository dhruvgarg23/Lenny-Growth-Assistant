"""
Hybrid retrieval — pgvector cosine + Postgres full-text (ts_rank) fused via RRF k=60.

One module behind one seam: HybridRetrieval is constructed with its
dependencies (session, embed function, result sizes) and exposes
search(query) -> tuple[Passage, ...]. No settings reads, no network
created inside — both are injected, so tests construct it directly.
"""
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.config import settings
from app.services.embeddings import embed_query
from app.observability.logger import get_logger, Timer

logger = get_logger("lenny.retrieval")

RRF_K = 60


@dataclass(frozen=True)
class Passage:
    """One ranked transcript chunk. The only shape callers must know."""

    id: str
    document_id: str
    content: str
    title: str
    source_path: str
    guest: Optional[str]
    vector_score: float = 0.0
    text_score: float = 0.0
    rrf_score: float = 0.0

    @property
    def confidence(self) -> float:
        return self.rrf_score


EmbedFn = Callable[[str], Awaitable[list[float]]]

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


def _to_passage(r: Any) -> Passage:
    return Passage(
        id=str(r["id"]),
        document_id=str(r["document_id"]),
        content=r["content"],
        title=r["title"],
        source_path=r["source_path"],
        guest=r["guest"],
        vector_score=float(r["vector_score"] or 0),
        text_score=float(r["text_score"] or 0),
        rrf_score=float(r["rrf_score"] or 0),
    )


class HybridRetrieval:
    """Hybrid dense + lexical search fused via RRF. Dependencies injected."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        embed: EmbedFn = embed_query,
        top_k: Optional[int] = None,
        candidate_k: Optional[int] = None,
    ):
        self._db = db
        self._embed = embed
        self._top_k = top_k or settings.retrieval_k
        self._candidate_k = candidate_k or settings.candidate_k

    async def search(self, query: str) -> tuple[Passage, ...]:
        if not query or not query.strip():
            logger.debug("retrieval_empty_query", extra={"event": "retrieval_skip", "reason": "empty_query"})
            return ()

        logger.info(
            "retrieval_start",
            extra={
                "event": "retrieval_start",
                "query_preview": query[:80],
                "query_len": len(query),
                "top_k": self._top_k,
                "candidate_k": self._candidate_k,
            },
        )

        # Embed query (may be slow — do before DB tx holds connection)
        with Timer() as embed_timer:
            try:
                qvec = await self._embed(query)
            except Exception as e:
                logger.error(
                    f"Embedding failed: {e}",
                    extra={"event": "embedding_error", "error": str(e), "duration_ms": embed_timer.elapsed_ms},
                    exc_info=True,
                )
                raise RuntimeError(f"Embedding failed: {e}") from e

        logger.debug(
            "query_embedded",
            extra={
                "event": "embedding_done",
                "dim": len(qvec),
                "duration_ms": embed_timer.elapsed_ms,
            },
        )

        qvec_str = "[" + ",".join(f"{x:.6f}" for x in qvec) + "]"

        with Timer() as search_timer:
            try:
                rows = (await self._db.execute(HYBRID_SQL, {"qvec": qvec_str, "qtext": query, "cand_k": self._candidate_k, "top_k": self._top_k, "rrf_k": RRF_K})).mappings().all()
                used_fallback = False
                # If hybrid returned nothing, fallback to vector-only
                if not rows:
                    logger.warning(
                        "hybrid_search_empty_fallback_to_vector",
                        extra={"event": "retrieval_fallback", "query_preview": query[:80]},
                    )
                    rows = (await self._db.execute(VECTOR_ONLY_SQL, {"qvec": qvec_str, "top_k": self._top_k, "rrf_k": RRF_K})).mappings().all()
                    used_fallback = True

                out = tuple(_to_passage(r) for r in rows)

                top_score = out[0].rrf_score if out else 0.0
                top_titles = [f"{c.title} ({c.guest or 'unknown'})" for c in out[:3]]

                logger.info(
                    f"retrieval_done hits={len(out)} top_score={top_score:.4f}",
                    extra={
                        "event": "retrieval_done",
                        "hits_count": len(out),
                        "top_score": round(top_score, 4),
                        "top_titles": top_titles,
                        "used_fallback": used_fallback,
                        "embed_duration_ms": embed_timer.elapsed_ms,
                        "db_search_duration_ms": search_timer.elapsed_ms,
                        "total_duration_ms": embed_timer.elapsed_ms + search_timer.elapsed_ms,
                    },
                )
                return out
            except Exception as e:
                logger.exception(f"Hybrid search SQL failed: {e}")
                # Try vector-only as last resort
                try:
                    rows = (await self._db.execute(VECTOR_ONLY_SQL, {"qvec": qvec_str, "top_k": self._top_k, "rrf_k": RRF_K})).mappings().all()
                    out = tuple(_to_passage(r) for r in rows)
                    logger.warning(
                        f"retrieval_recovered_via_vector_only hits={len(out)}",
                        extra={"event": "retrieval_recovered", "hits_count": len(out)},
                    )
                    return out
                except Exception as e2:
                    logger.error(
                        f"Vector-only fallback also failed: {e2}",
                        extra={"event": "retrieval_fatal_error", "error": str(e2)},
                        exc_info=True,
                    )
                    raise
