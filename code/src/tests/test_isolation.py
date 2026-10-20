"""Two users sharing one core must never see or touch each other's pages."""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.auth import current_user_id
from backend.main import app, limiter
from backend.library_map import MapService
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

    def bm25_search(self, query, user_id, rows=30, page_ids=None):
        terms = query.lower().split()
        return [dict(d, score=1.0) for d in self._mine(user_id)
                if any(t in d["text"].lower() for t in terms)
                and (page_ids is None or d["page_id"] in page_ids)][:rows]

    def knn_search(self, vector, user_id, k=30, page_ids=None):
        return [dict(d, score=0.9) for d in self._mine(user_id)
                if page_ids is None or d["page_id"] in page_ids][:k]

    def _heads(self, user_id):
        return [d for d in self._mine(user_id) if d["chunk_id"] == 0]

    def get_page_vector(self, page_id, user_id):
        head = self.get_page_head(page_id, user_id)
        return head.get("page_embedding") if head else None

    def related_pages(self, vector, user_id, exclude_page_id, k=5):
        scored = []
        for d in self._heads(user_id):
            if d["page_id"] == exclude_page_id or not d.get("page_embedding"):
                continue
            cos = sum(a * b for a, b in zip(vector, d["page_embedding"]))
            scored.append(dict(d, score=(1 + cos) / 2))
        return sorted(scored, key=lambda d: -d["score"])[:k]

    def scan_page_heads(self, user_id, fields, limit):
        return iter(sorted(self._heads(user_id), key=lambda d: d["timestamp"], reverse=True)[:limit])

    def add_page(self, user_id, page_id, title, vector, text=None):
        self.docs[f"{page_id}::0"] = {
            "id": f"{page_id}::0", "user_id": user_id, "page_id": page_id, "chunk_id": 0, "total_chunks": 1,
            "url": f"https://{user_id}.example.com/{page_id}", "title": title, "domain": f"{user_id}.example.com",
            "text": text or f"{title}. Some words about {title.lower()} for searching.",
            "timestamp": f"2024-01-{len(self.docs) % 28 + 1:02d}T00:00:00Z", "description": "",
            "page_embedding": list(vector),
        }

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
         patch("backend.main.map_service", MapService()), \
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


# ---- library map and related pages ---------------------------------------------

def _unit(i, j=None, mix=0.0):
    v = [0.0] * 384
    v[i] = 1.0
    if j is not None:
        v[j] = mix
    norm = sum(x * x for x in v) ** 0.5
    return [x / norm for x in v]


def _seed_library(fake, user, prefix, offset=0):
    """12 pages in 3 tight groups; vectors distinct per user (offset)."""
    ids = []
    for group in range(3):
        for j in range(4):
            page_id = f"{prefix}{group}{j}".ljust(32, "0")
            fake.add_page(user, page_id, f"{prefix} group {group} page {j}",
                          _unit(offset + group, 100 + offset + group * 4 + j, 0.2))
            ids.append(page_id)
    return ids


def test_map_contains_only_own_pages(env):
    fake, as_user = env
    a_ids = _seed_library(fake, A, "a")
    b_ids = _seed_library(fake, B, "b", offset=10)
    data = as_user(A).get("/map").json()
    assert data["status"] == "ok"
    assert {p["id"] for p in data["pages"]} == set(a_ids)
    assert not {e["a"] for e in data["edges"]} & set(b_ids)
    data_b = as_user(B).get("/map").json()
    assert {p["id"] for p in data_b["pages"]} == set(b_ids)


def test_map_search_only_scores_own_pages(env):
    fake, as_user = env
    _seed_library(fake, A, "a")
    b_ids = _seed_library(fake, B, "b", offset=10)
    with patch("backend.main._cached_query_embedding", return_value=tuple(_unit(10))):
        found = as_user(A).get("/map/search", params={"q": "b group 0"}).json()
    assert not set(found["pages"]) & set(b_ids)


def test_related_excludes_self_and_other_users(env):
    fake, as_user = env
    a_ids = _seed_library(fake, A, "a")
    # B has a page with exactly the same vector as A's first page.
    fake.add_page(B, "c" * 32, "B's twin page", fake.get_page_vector(a_ids[0], A))
    related = as_user(A).get(f"/memory/{a_ids[0]}/related", params={"k": 5}).json()["related"]
    ids = [r["id"] for r in related]
    assert a_ids[0] not in ids
    assert "c" * 32 not in ids
    assert ids and set(ids) <= set(a_ids)
    assert all(r["similarity"] >= 0.55 for r in related)
    assert related == sorted(related, key=lambda r: -r["similarity"])


def test_related_for_another_users_page_is_404(env):
    fake, as_user = env
    b_ids = _seed_library(fake, B, "b", offset=10)
    assert as_user(A).get(f"/memory/{b_ids[0]}/related").status_code == 404


def test_topic_search_cannot_use_another_users_topic(env):
    fake, as_user = env
    _seed_library(fake, A, "a")
    _seed_library(fake, B, "b", offset=10)
    b_topic = as_user(B).get("/map").json()["topics"][0]["id"]
    as_user(A).get("/map")
    response = as_user(A).post("/search", json={"query": "group", "topic": b_topic})
    assert response.status_code == 409
