from unittest.mock import MagicMock, patch

import pytest

from backend import retrieval
from backend.cleaning import is_prose
from backend.snippets import (
    SNIPPET_MAX_CHARS, SentenceEmbeddingCache, build_snippet, build_snippets, split_sentences, window,
)

# Each about 80-90 characters, so 3 consecutive sentences land in 200-280.
S1 = "The opening paragraph introduces the topic of the article for general readers."
S2 = "Neural networks learn patterns from examples by adjusting their internal weights."
S3 = "Training repeats this process many times until the predictions become accurate."
S4 = "Later sections compare several architectures and discuss their practical limits."
S5 = "The closing notes list further reading and a short glossary of technical terms."
TEXT = " ".join([S1, S2, S3, S4, S5])


# ---- eligibility --------------------------------------------------------------

@pytest.mark.parametrize("sentence,ok", [
    (S2, True),
    ("Too short to count as prose.", False),                                    # < 8 words
    ("Home | About | Contact | Pricing | Blog | Careers | Press | Help.", False),  # pipes
    ("Released 2021-03-04 build 4.2.1 rev 0x3f 99% 12/12 #42 v7 ok fine.", False),  # < 70% letters
    ("This sentence has plenty of words but no final punctuation at all", False),
    ('He said that the results were "surprisingly good for such a small model."', True),
])
def test_eligibility(sentence, ok):
    assert is_prose(sentence) is ok


# ---- best sentence and window -----------------------------------------------------

def test_best_sentence_by_query_term_match_then_window_of_consecutive_sentences():
    snippet = build_snippet(TEXT, "how do networks learn weights")
    assert snippet.startswith(S2)
    assert snippet == " ".join([S2, S3, S4])
    assert 200 <= len(snippet) <= 280


def test_most_distinct_terms_wins_over_first_match():
    snippet = build_snippet(TEXT, "training predictions accurate")
    assert snippet.startswith(S3)


def test_window_grows_backwards_when_best_is_last():
    snippet = build_snippet(TEXT, "glossary")
    assert snippet.endswith(S5)
    assert snippet == " ".join([S3, S4, S5])


def test_window_skips_ineligible_neighbours():
    text = " ".join([S1, "Menu | Login | Help.", S2, "Short one.", S3])
    snippet = build_snippet(text, "neural networks")
    assert snippet == S2  # both neighbours are ineligible, so the run stops


def test_window_stops_before_exceeding_max():
    long = "This deliberately long sentence keeps going " + "and going " * 20 + "until it finally ends."
    snippet = build_snippet(" ".join([S2, long]), "neural")
    assert snippet == S2


def test_single_overlong_sentence_is_trimmed():
    long = "Neural " + "networks keep learning " * 30 + "forever."
    snippet = build_snippet(long, "neural")
    assert len(snippet) <= SNIPPET_MAX_CHARS + 1
    assert snippet.endswith("…")


def test_window_function_directly():
    sentences = [S1, S2, S3]
    assert window(sentences, [True, True, True], 1) == " ".join(sentences)
    assert window(sentences, [False, True, False], 1) == S2


def test_ties_are_broken_by_embedding_similarity():
    query_vector = [1.0, 0.0]
    vectors = {S1: [0.1, 0.9], S2: [0.2, 0.8], S3: [0.95, 0.05], S4: [0.3, 0.7], S5: [0.0, 1.0]}
    embed = MagicMock(side_effect=lambda texts: [vectors[t] for t in texts])
    # No sentence contains "zebra", so every eligible sentence is tied at 0 matches.
    [snippet] = build_snippets([(TEXT, None)], "zebra", query_vector=query_vector, embed=embed)
    assert snippet.startswith(S3)
    embed.assert_called_once()


def test_embeddings_only_used_for_ties():
    embed = MagicMock()
    build_snippets([(TEXT, None)], "glossary", query_vector=[1.0], embed=embed)
    embed.assert_not_called()


def test_one_embedding_call_for_all_results():
    embed = MagicMock(side_effect=lambda texts: [[0.0, 1.0] for _ in texts])
    build_snippets([(TEXT, None), (TEXT, None)], "zebra", query_vector=[0.0, 1.0], embed=embed)
    assert embed.call_count == 1


def test_embedding_failure_falls_back_to_first_tied_sentence():
    embed = MagicMock(side_effect=RuntimeError("model down"))
    [snippet] = build_snippets([(TEXT, None)], "zebra", query_vector=[1.0], embed=embed)
    assert snippet.startswith(S1)


# ---- fallbacks --------------------------------------------------------------

def test_no_eligible_sentence_uses_description():
    junk = "Home | About\nLogin\nv1.2.3 2024"
    assert build_snippet(junk, "anything", description="A page about neural networks.") == \
        "A page about neural networks."


def test_no_eligible_sentence_and_no_description_shows_nothing():
    assert build_snippet("Home | About\nLogin", "anything", description="") is None
    assert build_snippet("", "anything") is None


def test_citation_markers_are_not_shown():
    text = "Neural networks learn patterns from examples by adjusting weights.[4] More text follows here today."
    snippet = build_snippet(text, "neural")
    assert "[4]" not in snippet


def test_split_sentences_keeps_reading_order():
    assert split_sentences("One two. Three four!\nFive six?") == ["One two.", "Three four!", "Five six?"]


def test_sentence_embedding_cache_encodes_each_sentence_once():
    encode = MagicMock(side_effect=lambda texts: [[float(len(t))] for t in texts])
    cache = SentenceEmbeddingCache(encode, max_items=2)
    assert cache(["a", "bb"]) == [(1.0,), (2.0,)]
    assert cache(["a"]) == [(1.0,)]
    assert encode.call_count == 1
    cache(["ccc"])  # evicts the least recently used ("bb")
    cache(["bb"])
    assert encode.call_count == 3


# ---- relevance floor -----------------------------------------------------------

def _page(page_id, bm25, sim):
    return {"page_id": page_id, "bm25_match": bm25, "vector_similarity": sim}


def test_relevance_floor_drops_weak_vector_only_pages():
    pages = [
        _page("bm25-only", True, None),
        _page("bm25-weak-vector", True, 0.1),
        _page("strong-vector", False, 0.8),
        _page("at-threshold", False, 0.55),
        _page("weak-vector", False, 0.54),
        _page("nothing", False, None),
    ]
    kept = [p["page_id"] for p in retrieval.apply_relevance_floor(pages, 0.55)]
    assert kept == ["bm25-only", "bm25-weak-vector", "strong-vector", "at-threshold"]


def test_relevance_floor_uses_config_default():
    with patch("backend.retrieval.MIN_VECTOR_SIMILARITY", 0.9):
        assert retrieval.apply_relevance_floor([_page("x", False, 0.8)]) == []


def test_knn_score_is_converted_to_cosine():
    assert retrieval.knn_score_to_cosine(1.0) == pytest.approx(1.0)
    assert retrieval.knn_score_to_cosine(0.5) == pytest.approx(0.0)
    assert retrieval.knn_score_to_cosine(0.775) == pytest.approx(0.55)


def _chunk(doc_id, page, **extra):
    doc = {"id": doc_id, "page_id": page, "url": f"https://e.com/{page}", "title": page,
           "domain": "e.com", "timestamp": "t", "text": S2}
    doc.update(extra)
    return doc


def test_hybrid_search_applies_floor_and_reports_similarity():
    solr = MagicMock()
    solr.bm25_search.return_value = [_chunk("lexical::0", "lexical")]
    solr.knn_search.return_value = [
        _chunk("strong::0", "strong", score=0.9),    # cosine 0.80
        _chunk("weak::0", "weak", score=0.7),        # cosine 0.40
        _chunk("lexical::0", "lexical", score=0.6),  # cosine 0.20, but matched BM25
    ]
    retrieval._cached_query_embedding.cache_clear()
    with patch("backend.retrieval.get_solr_client", return_value=solr), \
         patch("backend.retrieval.embed_query", return_value=[0.1] * 384):
        results = retrieval.hybrid_search("neural", "user-a", top_k=10, candidate_pool=10)
    by_id = {r["page_id"]: r for r in results}
    assert set(by_id) == {"strong", "lexical"}
    assert by_id["strong"]["vector_similarity"] == pytest.approx(0.8)
    assert by_id["lexical"]["vector_similarity"] == pytest.approx(0.2)
    assert by_id["lexical"]["bm25_match"] is True


def test_group_by_webpage_uses_best_similarity_of_any_chunk():
    candidates = [
        _chunk("p::0", "p", _vector_sim=0.3, _bm25_rank=None),
        _chunk("p::1", "p", _vector_sim=0.7, _bm25_rank=None),
    ]
    [page] = retrieval.group_by_webpage(candidates, {"p::0": 0.5, "p::1": 0.1})
    assert page["vector_similarity"] == pytest.approx(0.7)
    assert page["bm25_match"] is False
