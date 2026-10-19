"""API behaviour of the library map, related pages and topic search."""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.auth import current_user_id
from backend.library_map import MapService
from backend.main import app, limiter
from tests.test_library_map import make_heads

USER = "user-test"
PAGE_ID = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def solr():
    mock = MagicMock()
    mock.get_page_head.return_value = None
    mock.scan_page_heads.side_effect = lambda user_id, fields, limit: iter(make_heads())
    return mock


@pytest.fixture
def service():
    return MapService()


@pytest.fixture
def client(solr, service):
    limiter.reset()
    app.dependency_overrides[current_user_id] = lambda: USER
    with patch("backend.main.get_solr_client", return_value=solr), \
         patch("backend.ingest.get_solr_client", return_value=solr), \
         patch("backend.main.map_service", service), \
         patch("backend.main.is_gemini_available", return_value=False), \
         patch("backend.main.get_model"):
        with TestClient(app) as test_client:
            yield test_client
    app.dependency_overrides.clear()


def test_map_response_shape(client):
    data = client.get("/map").json()
    assert data["status"] == "ok"
    assert set(data) == {"status", "version", "topics", "pages", "edges", "counts"}
    assert set(data["topics"][0]) == {"id", "label", "count", "x", "y", "rx", "ry"}
    assert set(data["pages"][0]) == {"id", "title", "url", "domain", "saved_at", "x", "y", "topic"}
    assert set(data["edges"][0]) == {"a", "b", "kind"}
    assert data["counts"]["pages"] == len(data["pages"])
    assert data["counts"]["topics"] == len(data["topics"])


def test_map_too_few(client, solr):
    solr.scan_page_heads.side_effect = lambda user_id, fields, limit: iter(make_heads()[:5])
    assert client.get("/map").json()["status"] == "too_few"
    assert client.get("/map").json()["count"] == 5


def test_map_is_cached_and_invalidated_on_save(client, solr):
    first = client.get("/map").json()
    assert client.get("/map").json()["version"] == first["version"]
    assert solr.scan_page_heads.call_count == 1

    with patch("backend.ingest.embed_passages", side_effect=lambda texts: [[0.1] * 384 for _ in texts]):
        saved = client.post("/memory", json={"url": "https://e.com/x", "title": "T", "content": "hello world " * 40})
    assert saved.json()["status"] == "saved"
    assert client.get("/map").json()["version"] != first["version"]
    assert solr.scan_page_heads.call_count == 2


def test_unchanged_save_keeps_the_map(client, solr):
    first = client.get("/map").json()
    with patch("backend.main.ingest_page") as mock_ingest:
        mock_ingest.return_value = MagicMock(status="unchanged", message="m", page_id=PAGE_ID, url="u",
                                             title="t", domain="d", timestamp="ts", chunks=1)
        client.post("/memory", json={"url": "https://e.com/x", "title": "T", "content": "x"})
    assert client.get("/map").json()["version"] == first["version"]


def test_map_is_invalidated_on_delete_and_delete_all(client, solr):
    v1 = client.get("/map").json()["version"]
    solr.get_page_head.return_value = {"page_id": PAGE_ID}
    assert client.delete(f"/memory/{PAGE_ID}").status_code == 204
    v2 = client.get("/map").json()["version"]
    assert v2 != v1
    assert client.delete("/me/data").status_code == 204
    assert client.get("/map").json()["version"] != v2


def test_search_within_a_topic_prefilters_to_its_pages(client):
    data = client.get("/map").json()
    topic = data["topics"][0]
    expected = {p["id"] for p in data["pages"] if p["topic"] == topic["id"]}
    with patch("backend.main.hybrid_search", return_value=[]) as mock_search:
        response = client.post("/search", json={"query": "neural", "topic": topic["id"]})
    assert response.status_code == 200
    assert set(mock_search.call_args.kwargs["page_ids"]) == expected


def test_search_without_topic_has_no_page_filter(client):
    with patch("backend.main.hybrid_search", return_value=[]) as mock_search:
        client.post("/search", json={"query": "neural"})
    assert mock_search.call_args.kwargs["page_ids"] is None


def test_search_with_stale_topic_is_409(client, service):
    topic = client.get("/map").json()["topics"][0]["id"]
    service.invalidate(USER)  # e.g. a page was saved since
    with patch("backend.main.hybrid_search", return_value=[]) as mock_search:
        response = client.post("/search", json={"query": "neural", "topic": topic})
    assert response.status_code == 409
    mock_search.assert_not_called()


def test_search_with_topic_before_any_map_is_409(client):
    assert client.post("/search", json={"query": "q", "topic": "abc-0"}).status_code == 409


def test_map_search_endpoint(client):
    ml = np.zeros(384)
    ml[0], ml[300] = 0.8, 0.6
    with patch("backend.main._cached_query_embedding", return_value=tuple(ml)):
        data = client.get("/map/search", params={"q": "neural nets"}).json()
    assert data["query"] == "neural nets"
    assert data["topics"] and data["topics"][0]["score"] >= 0.55
    top_members = {p["id"] for p in client.get("/map").json()["pages"] if p["topic"] == data["topics"][0]["id"]}
    assert all("-ml-" in p for p in top_members)
    assert data["pages"] and all("-ml-" in p for p in data["pages"])


def test_map_search_requires_q(client):
    assert client.get("/map/search").status_code == 422
    assert client.get("/map/search", params={"q": "   "}).status_code == 400


def test_related_endpoint(client, solr):
    solr.get_page_head.return_value = {"page_id": PAGE_ID}
    solr.get_page_vector.return_value = [1.0] + [0.0] * 383
    solr.related_pages.return_value = [
        {"page_id": "b" * 32, "title": "Close", "url": "https://c.com", "domain": "c.com",
         "timestamp": "2024-01-01T00:00:00Z", "score": 0.95},
        {"page_id": "c" * 32, "title": "Weak", "url": "https://w.com", "domain": "w.com",
         "timestamp": "2024-01-01T00:00:00Z", "score": 0.7},   # cosine 0.4: below the floor
        {"page_id": PAGE_ID, "title": "Self", "url": "https://s.com", "domain": "s.com",
         "timestamp": "t", "score": 1.0},                       # never returned
    ]
    data = client.get(f"/memory/{PAGE_ID}/related", params={"k": 3}).json()
    assert data == {"page_id": PAGE_ID, "related": [{
        "id": "b" * 32, "title": "Close", "url": "https://c.com", "domain": "c.com",
        "saved_at": "2024-01-01T00:00:00Z", "similarity": 0.9,
    }]}
    solr.related_pages.assert_called_once_with(solr.get_page_vector.return_value, USER, exclude_page_id=PAGE_ID, k=3)


def test_related_without_a_page_vector_is_empty(client, solr):
    solr.get_page_head.return_value = {"page_id": PAGE_ID}
    solr.get_page_vector.return_value = None
    assert client.get(f"/memory/{PAGE_ID}/related").json()["related"] == []


def test_related_404_and_k_limits(client, solr):
    assert client.get(f"/memory/{PAGE_ID}/related").status_code == 404
    solr.get_page_head.return_value = {"page_id": PAGE_ID}
    assert client.get(f"/memory/{PAGE_ID}/related", params={"k": 0}).status_code == 422
    assert client.get(f"/memory/{PAGE_ID}/related", params={"k": 21}).status_code == 422


@pytest.mark.parametrize("method,path", [
    ("get", "/map"), ("get", "/map/search?q=x"), ("get", f"/memory/{PAGE_ID}/related"),
])
def test_new_endpoints_require_a_token(client, method, path):
    app.dependency_overrides.clear()
    assert getattr(client, method)(path).status_code == 401
