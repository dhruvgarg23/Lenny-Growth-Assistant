"""
Retrieval seam tests — HybridRetrieval with injected embed fn and mock session.
No DB, no network, no patching of module internals.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.retrieval import RRF_K, HybridRetrieval, Passage


def rrf_score(rank: int, k: int = RRF_K) -> float:
    return 1.0 / (k + rank)


def test_rrf_weights():
    # Rank 1 should be slightly better than rank 2 but not dominant when k=60
    assert rrf_score(1) > rrf_score(2)
    assert abs(rrf_score(1) - rrf_score(2)) < 0.0005  # damped


def test_rrf_fusion_both_lists():
    # Simulate hybrid: doc appears in both lists rank 1 + rank 5 vs doc only vector rank 1
    both = rrf_score(1) + rrf_score(5)
    single = rrf_score(1)
    assert both > single


def test_rrf_topk_stable():
    scores = [rrf_score(i) for i in range(1, 31)]
    # sorted descending == original order
    assert scores == sorted(scores, reverse=True)


def test_passage_confidence_is_rrf():
    p = Passage(id="c", document_id="d", content="x", title="T",
                source_path="p", guest=None, rrf_score=0.02)
    assert p.confidence == p.rrf_score == 0.02


def mock_db(rows_per_call):
    """AsyncMock session yielding canned mappings per execute call."""
    db = AsyncMock()
    results = []
    for rows in rows_per_call:
        m = MagicMock()
        m.mappings.return_value.all.return_value = rows
        results.append(m)
    db.execute.side_effect = results
    return db


async def fake_embed(query):
    assert query
    return [0.01] * 384


ROW = {"id": "c1", "content": "activation is key", "document_id": "d1",
       "title": "Onboarding", "source_path": "podcasts/a.md", "guest": "Lenny",
       "vector_score": 0.87, "text_score": 0.5, "rrf_score": 0.02}


@pytest.mark.asyncio
async def test_empty_query_short_circuits():
    db = AsyncMock()
    index = HybridRetrieval(db, embed=fake_embed)
    assert await index.search("   ") == ()
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_embedding_failure_raises():
    async def boom(q):
        raise RuntimeError("no model")

    db = AsyncMock()
    index = HybridRetrieval(db, embed=boom)
    with pytest.raises(RuntimeError, match="Embedding failed"):
        await index.search("hello")


@pytest.mark.asyncio
async def test_search_returns_passages():
    db = mock_db([[ROW]])
    index = HybridRetrieval(db, embed=fake_embed)
    out = await index.search("activation")
    assert len(out) == 1
    assert isinstance(out[0], Passage)
    assert out[0].id == "c1"
    assert out[0].confidence == out[0].rrf_score == 0.02
    assert db.execute.call_count == 1


@pytest.mark.asyncio
async def test_empty_hybrid_falls_back_to_vector_only():
    db = mock_db([[], [ROW]])
    index = HybridRetrieval(db, embed=fake_embed)
    out = await index.search("activation")
    assert len(out) == 1 and out[0].id == "c1"
    assert db.execute.call_count == 2
