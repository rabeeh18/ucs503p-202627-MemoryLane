from unittest.mock import MagicMock, patch

import pytest

from backend import rerank, retrieval


def _chunk(doc_id, page, text):
    return {"id": doc_id, "page_id": page, "url": f"https://e.com/{page}", "title": page.upper(),
            "domain": "e.com", "timestamp": "t", "text": text}


def _search(rerank_enabled, scores=None, top_n=20):
    solr = MagicMock()
    solr.bm25_search.return_value = [_chunk("a::0", "a", "alpha"), _chunk("b::0", "b", "beta")]
    solr.knn_search.return_value = [dict(_chunk("a::0", "a", "alpha"), score=0.9), dict(_chunk("c::0", "c", "gamma"), score=0.9)]
    retrieval._cached_query_embedding.cache_clear()
    timings = {}
    # KEYWORD_FULL_MATCH=0: these tests are about reranking, not the keyword floor
    # (the fixture's BM25 texts don't contain the query word).
    with patch("backend.retrieval.get_solr_client", return_value=solr), \
         patch("backend.retrieval.embed_query", return_value=[0.1] * 384), \
         patch("backend.retrieval.RERANK_ENABLED", rerank_enabled), \
         patch("backend.retrieval.RERANK_TOP_N", top_n), \
         patch("backend.retrieval.KEYWORD_FULL_MATCH", 0.0), \
         patch("backend.rerank.rerank_scores", side_effect=scores) as mock_scores:
        results = retrieval.hybrid_search("query", "user-a", top_k=3, candidate_pool=10, timings=timings)
    return results, timings, mock_scores


def test_rerank_disabled_keeps_rrf_order():
    results, timings, mock_scores = _search(False)
    assert [r["page_id"] for r in results] == ["a", "b", "c"]
    mock_scores.assert_not_called()
    assert timings["rerank_ms"] == 0.0


def test_rerank_reorders_pages_by_cross_encoder_score():
    def scores(query, passages):
        assert query == "query"
        assert passages[0] == "A\n\nalpha"  # title + chunk text
        by_text = {"A\n\nalpha": 0.1, "B\n\nbeta": 0.5, "C\n\ngamma": 0.9}
        return [by_text[p] for p in passages]

    results, timings, _ = _search(True, scores)
    assert [r["page_id"] for r in results] == ["c", "b", "a"]
    assert results[0]["rerank_score"] == pytest.approx(0.9)
    assert "rerank_ms" in timings


def test_rerank_keeps_pages_outside_top_n_after_reranked_ones():
    results, _, _ = _search(True, lambda q, passages: [0.5] * len(passages), top_n=1)
    assert results[0]["page_id"] == "a"
    assert {r["page_id"] for r in results} == {"a", "b", "c"}


def test_rerank_scores_maps_logits_into_unit_interval():
    model = MagicMock()
    model.predict.return_value = [-2.0, 0.0, 3.0]
    with patch("backend.rerank.get_reranker", return_value=model):
        scores = rerank.rerank_scores("q", ["x", "y", "z"])
    assert all(0.0 < s < 1.0 for s in scores)
    assert scores[0] < scores[1] < scores[2]
    model.predict.assert_called_once_with([("q", "x"), ("q", "y"), ("q", "z")])


def test_rerank_scores_empty():
    assert rerank.rerank_scores("q", []) == []


def test_rerank_keeps_similarity_looked_up_for_partial_keyword_matches():
    """A partial keyword match whose similarity was looked up after fusion must
    survive reranking, which regroups pages from their chunks."""
    solr = MagicMock()
    partial = _chunk("p::0", "p", "football history")  # 1 of 2 query words
    solr.bm25_search.return_value = [partial]

    def knn(vector, user, k, **kw):
        if kw.get("page_ids") == ["p"]:
            return [dict(partial, score=0.85)]  # cosine 0.70: about the query
        return []
    solr.knn_search.side_effect = knn
    retrieval._cached_query_embedding.cache_clear()
    with patch("backend.retrieval.embed_query", return_value=[0.1] * 384), \
         patch("backend.retrieval.QUERY_INTENT_ENABLED", False), \
         patch("backend.retrieval.RERANK_ENABLED", True), \
         patch("backend.rerank.rerank_scores", side_effect=lambda q, passages: [0.5] * len(passages)):
        results = retrieval.hybrid_search("football legends", "user-a", top_k=3, candidate_pool=10,
                                          solr=solr, snippets=False)
    assert [r["page_id"] for r in results] == ["p"]
    assert results[0]["vector_similarity"] == pytest.approx(0.70)
