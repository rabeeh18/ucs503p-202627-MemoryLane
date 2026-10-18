from unittest.mock import MagicMock

from backend.solr_client import SolrClient


def _client():
    solr = SolrClient(base_url="http://solr:8983/solr/core")
    solr.client = MagicMock()
    solr.client.post.return_value.json.return_value = {}
    solr.client.get.return_value.json.return_value = {"response": {"docs": []}}
    return solr


def test_upsert_adds_then_deletes_stale_chunks_without_commit():
    solr = _client()
    docs = [{"id": "page::chunk::0"}, {"id": "page::chunk::1"}]
    solr.upsert_page_chunks("page", docs)

    calls = solr.client.post.call_args_list
    assert len(calls) == 2
    add_url, delete_url = calls[0].args[0], calls[1].args[0]
    assert "commitWithin=1000" in add_url and "commit=true" not in add_url
    assert "commitWithin=1000" in delete_url and "commit=true" not in delete_url
    assert calls[0].kwargs["json"] == docs
    assert calls[1].kwargs["json"] == {
        "delete": {"query": 'webpage_id:"page" AND chunk_id:[2 TO *]'}
    }


def test_upsert_escapes_page_id_in_delete_query():
    solr = _client()
    solr.upsert_page_chunks('we"ird', [{"id": "x"}])
    query = solr.client.post.call_args_list[1].kwargs["json"]["delete"]["query"]
    assert query == 'webpage_id:"we\\"ird" AND chunk_id:[1 TO *]'


def test_client_has_no_explicit_commit_methods():
    assert not hasattr(SolrClient, "commit")
    assert not hasattr(SolrClient, "add_documents")
    assert not hasattr(SolrClient, "delete_by_query")


def test_bm25_query_uses_phrase_boost_and_blocks_field_queries():
    solr = _client()
    solr.bm25_search("id:* sleep\x00 memory", rows=5)
    params = solr.client.get.call_args.kwargs["params"]
    assert params["defType"] == "edismax"
    assert params["qf"] == "title^2 text"
    assert params["pf"] == "text^2 title^3"
    assert params["uf"] == "-*"
    assert "\x00" not in params["q"]
