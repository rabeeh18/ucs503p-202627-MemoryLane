"""Two users sharing one core must never see or touch each other's pages."""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.auth import current_user_id
from backend.main import app, limiter
from backend.solr_client import SolrClient

A, B = "user-a", "user-b"
URL = "https://example.com/shared-article"
TEXT = "Sleep consolidates memory and learning in the brain. " * 12


class FakeSolr:
    """In-memory stand-in for SolrClient that honours the user_id argument."""

    def __init__(self):
        self.docs: dict[str, dict] = {}

    def _mine(self, user_id):
        return [d for d in self.docs.values() if d["user_id"] == user_id]

    def ping(self):
        return True

    def upsert_page_chunks(self, page_id, docs, user_id):
        assert all(d["user_id"] == user_id for d in docs)
        for d in docs:
            self.docs[d["id"]] = {k: v for k, v in d.items() if k != "embedding"}
        for key in [k for k, d in self.docs.items()
                    if d["user_id"] == user_id and d["page_id"] == page_id and d["chunk_id"] >= len(docs)]:
            del self.docs[key]

    def get_page_head(self, page_id, user_id):
        return next((d for d in self._mine(user_id) if d["page_id"] == page_id and d["chunk_id"] == 0), None)

    def get_chunks_by_page_id(self, page_id, user_id):
        return sorted((d for d in self._mine(user_id) if d["page_id"] == page_id), key=lambda d: d["chunk_id"])

    def bm25_search(self, query, user_id, rows=30):
        terms = query.lower().split()
        return [dict(d, score=1.0) for d in self._mine(user_id)
                if any(t in d["text"].lower() for t in terms)][:rows]

    def knn_search(self, vector, user_id, k=30):
        return [dict(d, score=0.5) for d in self._mine(user_id)][:k]

    def list_pages(self, user_id, limit=20, offset=0):
        heads = sorted((d for d in self._mine(user_id) if d["chunk_id"] == 0),
                       key=lambda d: d["timestamp"], reverse=True)
        return len(heads), heads[offset:offset + limit]

    def scan(self, fields, user_id, rows=500):
        return iter(sorted(self._mine(user_id), key=lambda d: d["id"]))

    def delete_page(self, page_id, user_id):
        for key in [k for k, d in self.docs.items() if d["user_id"] == user_id and d["page_id"] == page_id]:
            del self.docs[key]

    def delete_user(self, user_id):
        for key in [k for k, d in self.docs.items() if d["user_id"] == user_id]:
            del self.docs[key]


@pytest.fixture
def env():
    limiter.reset()
    fake = FakeSolr()
    state = {"user": A}
    app.dependency_overrides[current_user_id] = lambda: state["user"]
    with patch("backend.main.get_solr_client", return_value=fake), \
         patch("backend.ingest.get_solr_client", return_value=fake), \
         patch("backend.retrieval.get_solr_client", return_value=fake), \
         patch("backend.ingest.embed_passages", side_effect=lambda texts: [[0.1] * 384 for _ in texts]), \
         patch("backend.retrieval.embed_query", return_value=[0.1] * 384), \
         patch("backend.main.get_model"):
        with TestClient(app) as client:

            def as_user(user):
                state["user"] = user
                return client

            yield fake, as_user
    app.dependency_overrides.clear()


def _save(client, url=URL, text=TEXT, title="Shared article"):
    response = client.post("/memory", json={"url": url, "title": title, "content": text})
    assert response.status_code == 200, response.text
    return response.json()["page"]


def test_same_url_gets_separate_pages_and_chunks(env):
    fake, as_user = env
    page_a = _save(as_user(A))
    page_b = _save(as_user(B))
    assert page_a["id"] != page_b["id"]
    assert page_a["url"] == page_b["url"] == URL
    owners = {(d["user_id"], d["page_id"]) for d in fake.docs.values()}
    assert owners == {(A, page_a["id"]), (B, page_b["id"])}


def test_search_never_returns_another_users_pages(env):
    _, as_user = env
    page_a = _save(as_user(A), url="https://a.example/sleep")
    _save(as_user(B), url="https://b.example/sleep")
    results = as_user(A).post("/search", json={"query": "sleep memory"}).json()["results"]
    assert [r["id"] for r in results] == [page_a["id"]]
    assert all(r["url"].startswith("https://a.example") for r in results)


def test_cannot_summarize_delete_or_check_status_of_another_users_page(env):
    fake, as_user = env
    page_b = _save(as_user(B))
    client = as_user(A)
    with patch("backend.main.is_gemini_available", return_value=True), \
         patch("backend.main.summarize", return_value="leak") as mock_summarize:
        assert client.post("/summarize", json={"query": "q", "id": page_b["id"]}).status_code == 404
    mock_summarize.assert_not_called()
    assert client.delete(f"/memory/{page_b['id']}").status_code == 404
    assert client.get("/memory/status", params={"url": URL}).json() == {"saved": False, "page": None}
    # B's page is untouched and still visible to B
    assert as_user(B).get("/memory/status", params={"url": URL}).json()["saved"] is True
    assert any(d["user_id"] == B for d in fake.docs.values())


def test_library_and_export_only_show_own_pages(env):
    _, as_user = env
    _save(as_user(A), url="https://a.example/1")
    _save(as_user(B), url="https://b.example/1")
    client = as_user(A)
    listing = client.get("/memories").json()
    assert listing["total"] == 1
    assert listing["pages"][0]["url"] == "https://a.example/1"
    exported = client.get("/me/export").json()["pages"]
    assert [p["url"] for p in exported] == ["https://a.example/1"]


def test_delete_my_data_leaves_other_user_untouched(env):
    fake, as_user = env
    _save(as_user(A))
    page_b = _save(as_user(B))
    assert as_user(A).delete("/me/data").status_code == 204
    assert {d["user_id"] for d in fake.docs.values()} == {B}
    assert as_user(B).get("/memories").json()["pages"][0]["id"] == page_b["id"]


def test_every_solr_request_from_the_client_carries_the_user_filter():
    """Assert on the HTTP layer: each scoped SolrClient call sends the user filter."""
    solr = SolrClient(base_url="http://solr:8983/solr/core")
    solr.client = MagicMock()
    solr.client.get.return_value.json.return_value = {"response": {"docs": [], "numFound": 0}}
    solr.client.post.return_value.json.return_value = {"response": {"docs": []}}
    doc = {"id": "p::0", "page_id": "p", "user_id": A}

    calls = [
        lambda: solr.bm25_search("q", A),
        lambda: solr.knn_search([0.1], A),
        lambda: solr.get_page_head("p", A),
        lambda: solr.get_chunks_by_page_id("p", A),
        lambda: solr.list_pages(A),
        lambda: list(solr.scan("id", A)),
        lambda: solr.upsert_page_chunks("p", [doc], A),
        lambda: solr.delete_page("p", A),
        lambda: solr.delete_user(A),
    ]
    for call in calls:
        solr.client.reset_mock()
        call()
        requests = solr.client.get.call_args_list + solr.client.post.call_args_list
        assert requests
        for request in requests:
            sent = json.dumps(request.kwargs.get("params") or {}) + json.dumps(request.kwargs.get("json"))
            assert ("{!term f=user_id}user-a" in sent) or ('user_id:\\"user-a\\"' in sent) or (
                # Adding chunks: every doc is stamped with the owner instead of filtered.
                isinstance(request.kwargs.get("json"), list)
                and all(d["user_id"] == A for d in request.kwargs["json"])
            ), sent
