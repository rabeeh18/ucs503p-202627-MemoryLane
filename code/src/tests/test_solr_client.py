from unittest.mock import MagicMock

import pytest

from backend.solr_client import SolrClient, is_valid_user_id

USER = "user-a"
FILTER = "{!term f=user_id}user-a"


def _client():
    solr = SolrClient(base_url="http://solr:8983/solr/core")
    solr.client = MagicMock()
    solr.client.post.return_value.json.return_value = {"response": {"docs": []}}
    solr.client.get.return_value.json.return_value = {"response": {"docs": [], "numFound": 0}}
    return solr


def _docs(n, user=USER, page="page"):
    return [{"id": f"{page}::{i}", "page_id": page, "user_id": user} for i in range(n)]


def test_upsert_adds_then_deletes_stale_chunks_without_commit():
    solr = _client()
    docs = _docs(2)
    solr.upsert_page_chunks("page", docs, USER)

    calls = solr.client.post.call_args_list
    assert len(calls) == 2
    add_url, delete_url = calls[0].args[0], calls[1].args[0]
    assert "commitWithin=1000" in add_url and "commit=true" not in add_url
    assert "commitWithin=1000" in delete_url and "commit=true" not in delete_url
    assert calls[0].kwargs["json"] == docs
    assert calls[1].kwargs["json"] == {
        "delete": {"query": 'user_id:"user-a" AND page_id:"page" AND chunk_id:[2 TO *]'}
    }


def test_upsert_rejects_chunks_of_another_user_or_page():
    solr = _client()
    with pytest.raises(ValueError):
        solr.upsert_page_chunks("page", _docs(1, user="user-b"), USER)
    with pytest.raises(ValueError):
        solr.upsert_page_chunks("page", _docs(1, page="other"), USER)
    solr.client.post.assert_not_called()


def test_upsert_escapes_page_id_in_delete_query():
    solr = _client()
    solr.upsert_page_chunks('we"ird', _docs(1, page='we"ird'), USER)
    query = solr.client.post.call_args_list[1].kwargs["json"]["delete"]["query"]
    assert query == 'user_id:"user-a" AND page_id:"we\\"ird" AND chunk_id:[1 TO *]'


def test_client_has_no_explicit_commit_methods():
    assert not hasattr(SolrClient, "commit")
    assert not hasattr(SolrClient, "add_documents")
    assert not hasattr(SolrClient, "delete_by_query")


def test_bm25_query_uses_phrase_boost_and_blocks_field_queries():
    solr = _client()
    solr.bm25_search("id:* sleep\x00 memory", USER, rows=5)
    params = solr.client.get.call_args.kwargs["params"]
    assert params["defType"] == "edismax"
    assert params["qf"] == "title^2 text"
    assert params["pf"] == "text^2 title^3"
    assert params["uf"] == "-*"
    assert params["fq"] == FILTER
    assert "\x00" not in params["q"]


def test_knn_uses_json_filter_as_pre_filter():
    solr = _client()
    solr.knn_search([0.1, 0.2], USER, k=7)
    payload = solr.client.post.call_args.kwargs["json"]
    assert payload["query"].startswith("{!knn f=embedding topK=7}")
    assert payload["filter"] == [FILTER]
    assert payload["limit"] == 7


def test_delete_user_uses_term_query_with_commit_within():
    solr = _client()
    solr.delete_user("abc-123")
    call = solr.client.post.call_args
    assert "commitWithin=1000" in call.args[0]
    assert call.kwargs["json"] == {"delete": {"query": "{!term f=user_id}abc-123"}}


def test_delete_page_is_owner_scoped():
    solr = _client()
    solr.delete_page("p1", USER)
    assert solr.client.post.call_args.kwargs["json"] == {
        "delete": {"query": 'user_id:"user-a" AND page_id:"p1"'}
    }


def test_get_page_head_fetches_chunk_zero_by_term():
    solr = _client()
    solr.client.get.return_value.json.return_value = {
        "response": {"docs": [{"id": "p::0", "page_id": ["p"], "content_hash": "h"}]}
    }
    head = solr.get_page_head("p", USER)
    params = solr.client.get.call_args.kwargs["params"]
    assert params["q"] == "{!term f=page_id}p"
    assert params["fq"] == [FILTER, "chunk_id:0"]
    assert "embedding," not in params["fl"] and not params["fl"].endswith("embedding")
    assert head == {"id": "p::0", "page_id": "p", "content_hash": "h"}


def test_get_page_head_missing_returns_none():
    assert _client().get_page_head("nope", USER) is None


def test_list_pages_newest_first():
    solr = _client()
    solr.client.get.return_value.json.return_value = {
        "response": {"numFound": 3, "docs": [{"page_id": "p"}]}
    }
    total, docs = solr.list_pages(USER, limit=20, offset=40)
    params = solr.client.get.call_args.kwargs["params"]
    assert params["fq"] == [FILTER, "chunk_id:0"]
    assert params["sort"].startswith("timestamp desc")
    assert (params["start"], params["rows"]) == (40, 20)
    assert total == 3 and docs == [{"page_id": "p"}]


def test_scan_pages_with_cursor_mark_until_exhausted():
    solr = _client()
    pages = [
        {"response": {"docs": [{"id": "a"}, {"id": "b"}]}, "nextCursorMark": "c1"},
        {"response": {"docs": [{"id": "c"}]}, "nextCursorMark": "c2"},
        {"response": {"docs": []}, "nextCursorMark": "c2"},
    ]
    solr.client.get.return_value.json.side_effect = pages
    ids = [d["id"] for d in solr.scan("id", USER, rows=2)]
    assert ids == ["a", "b", "c"]
    calls = solr.client.get.call_args_list
    assert [c.kwargs["params"]["cursorMark"] for c in calls] == ["*", "c1", "c2"]
    assert all(c.kwargs["params"]["sort"] == "id asc" for c in calls)
    assert all(c.kwargs["params"]["fq"] == [FILTER] for c in calls)


def test_scan_unscoped_has_no_user_filter():
    solr = _client()
    solr.client.get.return_value.json.return_value = {"response": {"docs": []}}
    list(solr.scan_unscoped("id"))
    assert "fq" not in solr.client.get.call_args.kwargs["params"]


@pytest.mark.parametrize("bad", ["", None, "a b", "x" * 65, "user:*", 'u"', "*"])
def test_scoped_calls_reject_malformed_user_ids(bad):
    solr = _client()
    for call in (
        lambda: solr.bm25_search("q", bad),
        lambda: solr.knn_search([0.1], bad),
        lambda: solr.get_page_head("p", bad),
        lambda: solr.get_chunks_by_page_id("p", bad),
        lambda: solr.list_pages(bad),
        lambda: list(solr.scan("id", bad)),
        lambda: solr.delete_page("p", bad),
        lambda: solr.delete_user(bad),
        lambda: solr.upsert_page_chunks("p", [], bad),
    ):
        with pytest.raises(ValueError):
            call()
    solr.client.get.assert_not_called()
    solr.client.post.assert_not_called()


def test_is_valid_user_id_accepts_cognito_subs():
    assert is_valid_user_id("4c1d6f2a-90b1-70e3-1a2b-3c4d5e6f7a8b")
    assert is_valid_user_id("eval")
    assert not is_valid_user_id("eval user")


# ---- page vectors, map scans, topic filters ---------------------------------------

def test_related_pages_prefilters_user_and_excludes_the_page():
    solr = _client()
    solr.related_pages([0.1, 0.2], USER, exclude_page_id="p1", k=5)
    payload = solr.client.post.call_args.kwargs["json"]
    assert payload["query"].startswith("{!knn f=page_embedding topK=5}")
    assert payload["filter"] == [FILTER, "-{!term f=page_id}p1"]


def test_get_page_vector_reads_chunk_zero():
    solr = _client()
    solr.client.get.return_value.json.return_value = {"response": {"docs": [{"page_embedding": [0.5, 0.5]}]}}
    assert solr.get_page_vector("p1", USER) == [0.5, 0.5]
    params = solr.client.get.call_args.kwargs["params"]
    assert params["fq"] == [FILTER, "chunk_id:0"]
    assert params["fl"] == "page_embedding"


def test_get_page_vector_missing():
    assert _client().get_page_vector("p1", USER) is None


def test_scan_page_heads_newest_first_and_capped():
    solr = _client()
    pages = [
        {"response": {"docs": [{"id": "a"}, {"id": "b"}]}, "nextCursorMark": "c1"},
        {"response": {"docs": [{"id": "c"}]}, "nextCursorMark": "c2"},
    ]
    solr.client.get.return_value.json.side_effect = pages
    ids = [d["id"] for d in solr.scan_page_heads(USER, "page_id,page_embedding", limit=3, rows=2)]
    assert ids == ["a", "b", "c"]
    calls = solr.client.get.call_args_list
    assert len(calls) == 2
    assert all(c.kwargs["params"]["fq"] == [FILTER, "chunk_id:0"] for c in calls)
    assert calls[0].kwargs["params"]["sort"] == "timestamp desc, id asc"
    assert calls[1].kwargs["params"]["rows"] == 1  # only what's left of the cap


def test_bm25_with_page_ids_posts_the_terms_filter():
    solr = _client()
    solr.client.post.return_value.json.return_value = {"response": {"docs": []}}
    solr.bm25_search("q", USER, page_ids=["p1", "p2"])
    solr.client.get.assert_not_called()
    data = solr.client.post.call_args.kwargs["data"]
    assert data["fq"] == [FILTER, "{!terms f=page_id}p1,p2"]


def test_knn_with_page_ids_adds_a_prefilter():
    solr = _client()
    solr.knn_search([0.1], USER, k=3, page_ids=["p1"])
    assert solr.client.post.call_args.kwargs["json"]["filter"] == [FILTER, "{!terms f=page_id}p1"]


def test_empty_topic_matches_nothing():
    solr = _client()
    solr.knn_search([0.1], USER, page_ids=[])
    assert solr.client.post.call_args.kwargs["json"]["filter"][1] == "-*:*"


@pytest.mark.parametrize("bad", ["", None, "x y"])
def test_new_scoped_calls_reject_malformed_user_ids(bad):
    solr = _client()
    for call in (
        lambda: solr.get_page_vector("p", bad),
        lambda: solr.related_pages([0.1], bad, exclude_page_id="p"),
        lambda: list(solr.scan_page_heads(bad, "page_id", 10)),
    ):
        with pytest.raises(ValueError):
            call()
    solr.client.get.assert_not_called()
    solr.client.post.assert_not_called()
