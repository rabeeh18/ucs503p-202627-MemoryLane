from unittest.mock import MagicMock, patch

import pytest

from backend import retrieval
from backend.retrieval import rrf_fuse, group_by_webpage
from backend.solr_client import normalize_solr_doc, unwrap_solr_value, sanitize_query


def test_rrf_rank_math():
    fused = rrf_fuse(["a", "b"], ["b", "c"], k=60, w_bm25=1.0, w_knn=1.0)
    assert fused["a"] == pytest.approx(1 / 61)
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["c"] == pytest.approx(1 / 62)
    assert max(fused, key=fused.get) == "b"


def test_rrf_chunk_in_only_one_list():
    fused = rrf_fuse(["a"], [], k=60, w_bm25=1.0, w_knn=1.0)
    assert fused == {"a": pytest.approx(1 / 61)}
    fused = rrf_fuse([], ["z"], k=10, w_bm25=1.0, w_knn=1.0)
    assert fused == {"z": pytest.approx(1 / 11)}


def test_rrf_empty():
    assert rrf_fuse([], [], k=60, w_bm25=1.0, w_knn=1.0) == {}


def test_rrf_weights():
    fused = rrf_fuse(["a", "b"], ["b", "a"], k=60, w_bm25=2.0, w_knn=0.5)
    assert fused["a"] == pytest.approx(2.0 / 61 + 0.5 / 62)
    assert fused["b"] == pytest.approx(2.0 / 62 + 0.5 / 61)
    assert fused["a"] > fused["b"]
    # Zero weight disables a list entirely
    fused = rrf_fuse(["a"], ["b"], k=60, w_bm25=0.0, w_knn=1.0)
    assert fused["a"] == 0.0
    assert fused["b"] > 0.0


def _chunk(doc_id, page, **extra):
    doc = {
        "id": doc_id,
        "page_id": page,
        "url": f"https://example.com/{page}",
        "title": page.title(),
        "domain": "example.com",
        "timestamp": "t",
        "text": f"text of {doc_id}",
    }
    doc.update(extra)
    return doc


def test_group_by_webpage_highest_chunk_wins():
    candidates = [
        _chunk("page1::chunk::0", "page1", _bm25_rank=3, _knn_rank=None),
        _chunk("page1::chunk::1", "page1", _bm25_rank=1, _knn_rank=2),
        _chunk("page2::chunk::0", "page2", _bm25_rank=2, _knn_rank=1),
    ]
    fused = {
        "page1::chunk::0": 0.15,
        "page1::chunk::1": 0.85,
        "page2::chunk::0": 0.40,
    }
    grouped = group_by_webpage(candidates, fused, second_chunk_weight=0.0)
    assert grouped[0]["page_id"] == "page1"
    assert grouped[0]["fused_score"] == 0.85
    assert grouped[0]["id"] == "page1::chunk::1"
    assert grouped[0]["text"] == "text of page1::chunk::1"
    assert grouped[0]["bm25_rank"] == 1
    assert grouped[0]["knn_rank"] == 2
    assert grouped[1]["page_id"] == "page2"


def test_group_by_webpage_adds_weighted_second_chunk():
    candidates = [
        _chunk("a::0", "a"),
        _chunk("a::1", "a"),
        _chunk("a::2", "a"),
        _chunk("b::0", "b"),
    ]
    fused = {"a::0": 0.2, "a::1": 0.5, "a::2": 0.1, "b::0": 0.6}
    grouped = group_by_webpage(candidates, fused, second_chunk_weight=0.3)
    by_page = {g["page_id"]: g for g in grouped}
    # best 0.5 + 0.3 * second-best 0.2; the third chunk is ignored
    assert by_page["a"]["fused_score"] == pytest.approx(0.56)
    assert by_page["a"]["id"] == "a::1"
    # single-chunk page gets no second-chunk bonus
    assert by_page["b"]["fused_score"] == pytest.approx(0.6)
    assert [g["page_id"] for g in grouped] == ["b", "a"]

    grouped = group_by_webpage(candidates, {**fused, "a::0": 0.4}, second_chunk_weight=0.3)
    assert grouped[0]["page_id"] == "a"  # 0.5 + 0.12 = 0.62 > 0.6


def test_sanitize_query_strips_control_chars_and_caps_length():
    assert sanitize_query("hello\x00\nworld\t") == "hello  world"
    assert len(sanitize_query("a" * 2000)) == 500


def test_hybrid_search_fuses_ranks_and_reports_timings():
    solr = MagicMock()
    sentence = "Sleep and memory are closely linked in the human brain according to research."
    solr.bm25_search.return_value = [
        _chunk("p1::0", "p1", text=sentence),
        _chunk("p2::0", "p2"),
    ]
    solr.knn_search.return_value = [
        _chunk("p2::0", "p2", score=0.9),
        _chunk("p3::0", "p3", score=0.85),
        _chunk("p4::0", "p4", score=0.7),  # cosine 0.4: below the floor, no BM25 match
    ]
    retrieval._cached_query_embedding.cache_clear()
    timings = {}
    with patch("backend.retrieval.get_solr_client", return_value=solr), \
         patch("backend.retrieval.embed_query", return_value=[0.1] * 384):
        results = retrieval.hybrid_search("sleep memory", "user-a", top_k=3, candidate_pool=10, timings=timings)
    assert [r["page_id"] for r in results] == ["p2", "p1", "p3"]
    assert results[0]["bm25_rank"] == 2 and results[0]["knn_rank"] == 1
    assert results[1]["knn_rank"] is None
    assert results[2]["bm25_rank"] is None
    assert results[1]["snippet"] == sentence
    assert results[2]["vector_similarity"] == pytest.approx(0.7)
    assert [r["rank"] for r in results] == [1, 2, 3]
    assert set(timings) == {"embed_ms", "bm25_ms", "knn_ms", "intent_ms", "fuse_ms", "rerank_ms", "snippet_ms", "total_ms"}


def test_query_embedding_is_cached():
    retrieval._cached_query_embedding.cache_clear()
    with patch("backend.retrieval.embed_query", return_value=[0.5] * 384) as mock_embed:
        first = retrieval._cached_query_embedding("same query")
        second = retrieval._cached_query_embedding("same query")
    assert first == second
    assert isinstance(first, tuple)
    mock_embed.assert_called_once()


def test_unwrap_single_element_list():
    assert unwrap_solr_value(["Artificial Intelligence"], "title") == "Artificial Intelligence"
    assert unwrap_solr_value(["https://example.com"], "url") == "https://example.com"
    assert unwrap_solr_value("already-scalar", "id") == "already-scalar"


def test_unwrap_keeps_embedding_vector():
    vector = [0.1] * 384
    assert unwrap_solr_value(vector, "embedding") == vector


def test_normalize_solr_doc_flattens_string_fields():
    doc = normalize_solr_doc({
        "id": "doc1",
        "title": ["Artificial Intelligence"],
        "url": ["https://example.com/ai"],
        "domain": ["example.com"],
        "page_id": ["example.com_ai"],
        "text": ["Some page text"],
        "timestamp": ["2024-01-01T00:00:00Z"],
        "chunk_id": [0],
        "total_chunks": [1],
        "score": 1.2,
        "embedding": [0.1, 0.2],
    })
    assert doc["title"] == "Artificial Intelligence"
    assert doc["url"] == "https://example.com/ai"
    assert doc["domain"] == "example.com"
    assert doc["page_id"] == "example.com_ai"
    assert doc["text"] == "Some page text"
    assert doc["timestamp"] == "2024-01-01T00:00:00Z"
    assert doc["chunk_id"] == 0
    assert doc["total_chunks"] == 1
    assert doc["score"] == 1.2
    assert doc["embedding"] == [0.1, 0.2]


def test_group_by_webpage_accepts_solr_list_fields():
    raw = {
        "id": "page1::chunk::0",
        "page_id": ["page1"],
        "url": ["https://example.com/1"],
        "title": ["Artificial Intelligence"],
        "domain": ["example.com"],
        "timestamp": ["t1"],
    }
    doc = normalize_solr_doc(raw)
    grouped = group_by_webpage([doc], {doc["id"]: 0.9})
    assert grouped[0]["title"] == "Artificial Intelligence"
    assert grouped[0]["page_id"] == "page1"


def test_hybrid_search_passes_user_to_both_searches():
    solr = MagicMock()
    solr.bm25_search.return_value = []
    solr.knn_search.return_value = []
    retrieval._cached_query_embedding.cache_clear()
    with patch("backend.retrieval.embed_query", return_value=[0.1] * 384):
        assert retrieval.hybrid_search("q", "user-a", solr=solr) == []
    assert solr.bm25_search.call_args.args[1] == "user-a"
    assert solr.knn_search.call_args.args[1] == "user-a"


# ---- site words, time phrases and URLs in queries -----------------------------

def _intent_solr(domains, main_bm25=(), main_knn=(), site_bm25=(), site_knn=(), recent=(), head=None):
    solr = MagicMock()
    solr.base_url = "http://solr/test"
    solr.list_domains.return_value = [(d, 1) for d in domains]
    solr.bm25_search.side_effect = lambda q, u, rows, **kw: list(site_bm25 if kw.get("filters") else main_bm25)
    solr.knn_search.side_effect = lambda v, u, k, **kw: list(site_knn if kw.get("filters") else main_knn)
    solr.recent_pages.return_value = list(recent)
    solr.get_page_head.return_value = head
    return solr


def _search(solr, query, **kw):
    retrieval._site_cache.clear()
    with patch("backend.retrieval.embed_query", return_value=[0.1] * 384):
        return retrieval.hybrid_search(query, "user-a", top_k=5, candidate_pool=10, solr=solr,
                                       snippets=False, **kw)


def test_site_word_ranks_that_sites_page_first():
    other = [_chunk(f"o{i}::0", f"o{i}", score=0.9 - i / 100) for i in range(4)]
    reddit = _chunk("r::0", "r", domain="reddit.com", score=0.8)
    solr = _intent_solr(["reddit.com", "example.com"], main_bm25=other, main_knn=other + [reddit],
                        site_bm25=[reddit], site_knn=[reddit])
    results = _search(solr, "reddit post on rust lifetimes")
    assert results[0]["page_id"] == "r"
    site_calls = [c for c in solr.bm25_search.call_args_list if c.kwargs.get("filters")]
    assert site_calls[0].args[0] == "rust lifetimes"
    assert site_calls[0].kwargs["filters"] == ["{!terms f=domain}reddit.com"]


def test_query_without_intent_makes_no_extra_searches():
    page = _chunk("a::0", "a", score=0.9)
    solr = _intent_solr(["reddit.com"], main_bm25=[page], main_knn=[page])
    _search(solr, "rust lifetimes")
    assert solr.bm25_search.call_count == 1 and solr.knn_search.call_count == 1
    solr.recent_pages.assert_not_called()


def test_time_only_query_keeps_pages_from_then_past_the_floor():
    old = _chunk("t::0", "t", timestamp="2026-08-30T10:00:00Z")
    noise = _chunk("n::0", "n", score=0.6)  # cosine 0.2: below the floor
    solr = _intent_solr(["example.com"], main_knn=[noise], recent=[old])
    results = _search(solr, "what i read on 30 august")
    assert [r["page_id"] for r in results] == ["t"]
    filters = solr.recent_pages.call_args.args[1]
    assert filters[0].startswith("timestamp:[") and filters[0].endswith("}")
    assert solr.recent_pages.call_args.kwargs["near"].endswith("T12:00:00Z")


def test_typed_url_puts_that_page_first():
    others = [_chunk(f"o{i}::0", f"o{i}", score=0.95) for i in range(3)]
    mine = _chunk("m::0", "m", domain="github.com", url="https://github.com/tokio-rs/axum")
    solr = _intent_solr(["github.com"], main_bm25=others, main_knn=others, head=mine)
    results = _search(solr, "github.com/tokio-rs/axum")
    assert results[0]["page_id"] == "m"


def test_intent_lookup_failure_does_not_break_search():
    page = _chunk("a::0", "a", score=0.9)
    solr = _intent_solr([], main_bm25=[page], main_knn=[page])
    solr.list_domains.side_effect = RuntimeError("solr down")
    assert [r["page_id"] for r in _search(solr, "reddit rust")] == ["a"]


def test_intent_can_be_turned_off():
    page = _chunk("a::0", "a", score=0.9)
    solr = _intent_solr(["reddit.com"], main_bm25=[page], main_knn=[page])
    with patch("backend.retrieval.QUERY_INTENT_ENABLED", False):
        _search(solr, "reddit rust from yesterday")
    solr.list_domains.assert_not_called()
    assert solr.bm25_search.call_count == 1


def test_sites_are_cached_until_forgotten():
    solr = _intent_solr(["reddit.com"])
    retrieval._site_cache.clear()
    assert retrieval.user_domains(solr, "user-a") == ["reddit.com"]
    retrieval.user_domains(solr, "user-a")
    assert solr.list_domains.call_count == 1
    retrieval.forget_user_sites("user-a")
    retrieval.user_domains(solr, "user-a")
    assert solr.list_domains.call_count == 2
