"""
Test retrieval helpers without DB — focus on RRF fusion math and abstention gating.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.retrieval import RRF_K

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

@pytest.mark.asyncio
async def test_hybrid_search_empty_query():
    from app.services.retrieval import hybrid_search
    db = AsyncMock()
    out = await hybrid_search(db, "   ")
    assert out == []

@pytest.mark.asyncio
async def test_hybrid_search_embedding_failure():
    from app.services.retrieval import hybrid_search
    db = AsyncMock()
    with patch("app.services.retrieval.embed_query", new=AsyncMock(side_effect=RuntimeError("no model"))):
        with pytest.raises(RuntimeError, match="Embedding failed"):
            await hybrid_search(db, "hello")

@pytest.mark.asyncio
async def test_hybrid_search_returns_mapped():
    from app.services.retrieval import hybrid_search
    fake_rows = [
        {"id": "c1", "content": "activation is key", "document_id": "d1", "title": "Onboarding", "source_path": "podcasts/a.md", "guest": "Lenny", "vector_score": 0.87, "text_score": 0.5, "rrf_score": 0.02},
    ]
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = fake_rows
    db = AsyncMock()
    db.execute.return_value = mock_result

    fake_vec = [0.01] * 384
    with patch("app.services.retrieval.embed_query", new=AsyncMock(return_value=fake_vec)):
        out = await hybrid_search(db, "activation")
        assert len(out) == 1
        assert out[0]["id"] == "c1"
        assert out[0]["confidence"] == out[0]["rrf_score"]
