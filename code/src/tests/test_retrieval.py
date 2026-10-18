from unittest.mock import MagicMock, patch

import pytest

from backend import retrieval
from backend.retrieval import rrf_fuse, group_by_webpage, build_snippet
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


def test_snippet_picks_first_sentence_with_query_term():
    text = "Intro sentence about nothing. Machine learning is fun. Learning again here."
    assert build_snippet(text, "learn") == "Machine learning is fun."


def test_snippet_prefix_match_is_case_insensitive():
    text = "First one. SLEEPING well helps memory consolidation."
    assert build_snippet(text, "Sleep") == "SLEEPING well helps memory consolidation."


def test_snippet_ignores_short_terms_and_falls_back_to_first_sentence():
    text = "The opening line. Another line with ai in it."
    assert build_snippet(text, "ai") == "The opening line."
    assert build_snippet(text, "zebra") == "The opening line."


def test_snippet_trims_at_word_boundary():
    sentence = " ".join(["word"] * 100) + "."
    snippet = build_snippet(sentence, "nothing")
    assert snippet.endswith("…")
    assert len(snippet) <= 241
    assert snippet[:-1].split() == ["word"] * len(snippet[:-1].split())


def test_snippet_long_sentence_centres_on_late_match():
    sentence = " ".join(["filler"] * 80) + " neuroscience matters here."
    snippet = build_snippet(sentence, "neuroscience")
    assert snippet.startswith("…")
    assert "neuroscience" in snippet


def test_snippet_empty_text():
    assert build_snippet("", "query") is None
    assert build_snippet("   \n  ", "query") is None


def test_sanitize_query_strips_control_chars_and_caps_length():
    assert sanitize_query("hello\x00\nworld\t") == "hello  world"
    assert len(sanitize_query("a" * 2000)) == 500


def test_hybrid_search_fuses_ranks_and_reports_timings():
    solr = MagicMock()
    solr.bm25_search.return_value = [
        _chunk("p1::0", "p1", text="Sleep and memory are linked."),
        _chunk("p2::0", "p2"),
    ]
    solr.knn_search.return_value = [
        _chunk("p2::0", "p2"),
        _chunk("p3::0", "p3"),
    ]
    retrieval._cached_query_embedding.cache_clear()
    timings = {}
    with patch("backend.retrieval.get_solr_client", return_value=solr), \
         patch("backend.retrieval.embed_query", return_value=[0.1] * 384):
        results = retrieval.hybrid_search("sleep memory", top_k=3, candidate_pool=10, timings=timings)
    assert [r["page_id"] for r in results] == ["p2", "p1", "p3"]
    assert results[0]["bm25_rank"] == 2 and results[0]["knn_rank"] == 1
    assert results[1]["knn_rank"] is None
    assert results[2]["bm25_rank"] is None
    assert results[1]["snippet"] == "Sleep and memory are linked."
    assert [r["rank"] for r in results] == [1, 2, 3]
    assert set(timings) == {"embed_ms", "bm25_ms", "knn_ms", "fuse_ms", "rerank_ms", "total_ms"}


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
