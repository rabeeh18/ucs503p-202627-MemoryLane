import hashlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.auth import current_user_id
from backend.main import app, limiter
from backend.url_utils import generate_page_id

USER = "user-test"
LONG_TEXT = "hello world " * 40
PAGE_ID = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def solr():
    mock = MagicMock()
    mock.get_page_head.return_value = None
    with patch("backend.main.get_solr_client", return_value=mock), \
         patch("backend.ingest.get_solr_client", return_value=mock):
        yield mock


@pytest.fixture
def client():
    limiter.reset()
    app.dependency_overrides[current_user_id] = lambda: USER
    with patch("backend.main.get_model"):
        with TestClient(app) as test_client:
            yield test_client
    app.dependency_overrides.clear()


def _fake_embed(texts):
    return [[0.1] * 384 for _ in texts]


def _head(**extra):
    doc = {
        "page_id": PAGE_ID, "url": "https://example.com/guide", "title": "Guide",
        "domain": "example.com", "timestamp": "2024-01-01T00:00:00Z", "total_chunks": 2,
    }
    doc.update(extra)
    return doc


def test_health_contract(client):
    with patch("backend.main.get_solr_client") as mock_solr, \
         patch("backend.main.is_model_loaded", return_value=True), \
         patch("backend.main.is_gemini_available", return_value=False):
        mock_solr.return_value.ping.return_value = True
        response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["solr"] is True
    assert data["embedding_model"] is True
    assert data["gemini"] is False


def test_health_is_public(client):
    app.dependency_overrides.clear()
    with patch("backend.main.get_solr_client"):
        assert client.get("/health").status_code == 200


@pytest.mark.parametrize("method,path,body", [
    ("post", "/memory", {"url": "https://e.com", "title": "t", "content": "c"}),
    ("get", "/memory/status?url=https://e.com", None),
    ("delete", f"/memory/{PAGE_ID}", None),
    ("get", "/memories", None),
    ("post", "/search", {"query": "q"}),
    ("post", "/summarize", {"query": "q", "id": PAGE_ID}),
    ("get", "/me/export", None),
    ("delete", "/me/data", None),
])
def test_every_endpoint_but_health_requires_a_token(client, solr, method, path, body):
    app.dependency_overrides.clear()
    kwargs = {"json": body} if body is not None else {}
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    solr.assert_not_called()
    assert not solr.method_calls


# ---- POST /memory -----------------------------------------------------------

def test_memory_requires_fields(client, solr):
    response = client.post("/memory", json={"url": "", "title": "t", "content": "c" * 250})
    assert response.status_code == 400

    response = client.post("/memory", json={"url": "https://ex.com", "title": "t", "content": "too short"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Not enough readable text on this page"

    with patch("backend.ingest.embed_passages", side_effect=_fake_embed):
        response = client.post("/memory", json={"url": "https://ex.com/page", "title": "", "content": LONG_TEXT})
    assert response.status_code == 200
    assert response.json()["page"]["title"] == "ex.com"


def test_memory_saves_under_the_token_user(client, solr):
    with patch("backend.ingest.embed_passages", side_effect=_fake_embed):
        response = client.post("/memory", json={
            "url": "https://www.example.com/guide?utm_source=x",
            "title": "Guide",
            "content": LONG_TEXT,
        })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "saved"
    page = data["page"]
    assert page["url"] == "https://example.com/guide"
    assert page["id"] == generate_page_id(USER, "https://example.com/guide")
    assert set(page) == {"id", "url", "title", "domain", "timestamp", "chunks"}
    page_id, docs, user_id = solr.upsert_page_chunks.call_args[0]
    assert user_id == USER
    assert page_id == page["id"]
    assert page["chunks"] == len(docs)
    assert all(d["user_id"] == USER for d in docs)


def test_memory_ignores_user_id_in_body(client, solr):
    with patch("backend.ingest.embed_passages", side_effect=_fake_embed):
        client.post("/memory", json={
            "url": "https://example.com/x", "title": "t", "content": LONG_TEXT, "user_id": "someone-else",
        })
    assert solr.upsert_page_chunks.call_args[0][2] == USER


def test_memory_unchanged_page_is_not_reindexed(client, solr):
    from backend.cleaning import clean_content
    from backend.config import EMBEDDING_MODEL
    solr.get_page_head.return_value = _head(
        content_hash=hashlib.sha256(clean_content(None, LONG_TEXT).encode()).hexdigest(),
        embedding_model=EMBEDDING_MODEL,
    )
    with patch("backend.ingest.embed_passages") as mock_embed:
        response = client.post("/memory", json={
            "url": "https://example.com/guide/#section?utm_campaign=x",
            "title": "Guide again",
            "content": LONG_TEXT,
        })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unchanged"
    assert data["page"]["chunks"] == 2
    mock_embed.assert_not_called()
    solr.upsert_page_chunks.assert_not_called()


def test_memory_youtube_skip_has_no_page(client, solr):
    with patch("backend.ingest.process_youtube_video",
               return_value=(None, None, "Skipped: YouTube video is over 2 hours long")):
        response = client.post("/memory", json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": "x", "content": "x",
        })
    assert response.status_code == 200
    assert response.json() == {
        "status": "skipped", "message": "Skipped: YouTube video is over 2 hours long", "page": None,
    }


def test_memory_lookalike_youtube_host_is_not_treated_as_youtube(client, solr):
    with patch("backend.ingest.process_youtube_video") as mock_yt, \
         patch("backend.ingest.embed_passages", side_effect=_fake_embed):
        response = client.post("/memory", json={
            "url": "https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
            "title": "t", "content": LONG_TEXT,
        })
    assert response.status_code == 200
    mock_yt.assert_not_called()


def test_memory_input_limits(client, solr):
    too_long_url = "https://example.com/" + "a" * 2048
    assert client.post("/memory", json={"url": too_long_url, "title": "t", "content": "c"}).status_code == 422
    assert client.post("/memory", json={"url": "https://e.com", "title": "t" * 501, "content": "c"}).status_code == 422
    assert client.post("/memory", json={"url": "https://e.com", "title": "t", "content": "c" * 500_001}).status_code == 422
    assert client.post("/memory", json={"url": "https://e.com", "title": "t", "content": "c",
                                        "html": "h" * 3_000_001}).status_code == 422
    assert client.post("/search", json={"query": "q" * 501}).status_code == 422


# ---- status, delete, list -----------------------------------------------------

def test_status_normalizes_url_like_ingest(client, solr):
    solr.get_page_head.return_value = _head()
    response = client.get("/memory/status", params={"url": "https://www.example.com/guide/?utm_source=x#top"})
    assert response.status_code == 200
    assert response.json()["saved"] is True
    assert response.json()["page"]["id"] == PAGE_ID
    page_id, user_id = solr.get_page_head.call_args[0]
    assert page_id == generate_page_id(USER, "https://example.com/guide")
    assert user_id == USER


def test_status_uses_canonical_url_when_given(client, solr):
    client.get("/memory/status", params={"url": "https://example.com/a?x=1", "canonical_url": "/canon"})
    assert solr.get_page_head.call_args[0][0] == generate_page_id(USER, "https://example.com/canon")


def test_status_not_saved(client, solr):
    response = client.get("/memory/status", params={"url": "https://example.com/new"})
    assert response.json() == {"saved": False, "page": None}


def test_delete_own_page(client, solr):
    solr.get_page_head.return_value = _head()
    response = client.delete(f"/memory/{PAGE_ID}")
    assert response.status_code == 204
    solr.delete_page.assert_called_once_with(PAGE_ID, USER)


def test_delete_missing_or_foreign_page_is_404(client, solr):
    assert client.delete(f"/memory/{PAGE_ID}").status_code == 404
    assert client.delete("/memory/not-a-page-id").status_code == 404
    solr.delete_page.assert_not_called()


def test_list_memories_newest_first_contract(client, solr):
    solr.list_pages.return_value = (42, [_head()])
    response = client.get("/memories", params={"limit": 5, "offset": 10})
    assert response.status_code == 200
    assert response.json() == {"total": 42, "pages": [{
        "id": PAGE_ID, "url": "https://example.com/guide", "title": "Guide",
        "domain": "example.com", "timestamp": "2024-01-01T00:00:00Z", "chunks": None,
    }]}
    solr.list_pages.assert_called_once_with(USER, limit=5, offset=10)
    assert client.get("/memories", params={"limit": 0}).status_code == 422
    assert client.get("/memories", params={"limit": 101}).status_code == 422


# ---- search -------------------------------------------------------------------

HYBRID_RESULT = {
    "rank": 1, "page_id": PAGE_ID, "title": "Guide", "url": "https://example.com/guide",
    "domain": "example.com", "timestamp": "2024-01-01T00:00:00Z", "snippet": "The guide explains things.",
    "bm25_rank": 2, "knn_rank": None, "fused_score": 0.016,
}


def test_search_requires_query(client):
    assert client.post("/search", json={"query": "   "}).status_code == 400


def test_search_scopes_to_token_user_and_matches_contract(client):
    with patch("backend.main.hybrid_search", return_value=[HYBRID_RESULT]) as mock_search:
        response = client.post("/search", json={"query": "guide"})
    assert response.status_code == 200
    assert mock_search.call_args[0][1] == USER
    item = response.json()["results"][0]
    assert set(item) == {"rank", "id", "url", "title", "domain", "timestamp", "snippet", "summary"}
    assert item["id"] == PAGE_ID
    assert item["summary"] is None


def test_search_summarize_defaults_off(client):
    with patch("backend.main.hybrid_search", return_value=[HYBRID_RESULT]), \
         patch("backend.main._summary_for_webpage") as mock_sum:
        client.post("/search", json={"query": "guide"})
    mock_sum.assert_not_called()


def test_search_summarize_uses_owner_scoped_text(client):
    with patch("backend.main.hybrid_search", return_value=[HYBRID_RESULT]), \
         patch("backend.main._summary_for_webpage", return_value="S") as mock_sum:
        response = client.post("/search", json={"query": "guide", "summarize": True})
    assert response.json()["results"][0]["summary"] == "S"
    mock_sum.assert_called_once_with("guide", PAGE_ID, USER)


def test_search_debug_includes_ranks_and_timings(client):
    def fake_search(query, user_id, top_k=None, timings=None):
        timings.update({"embed_ms": 1.0, "bm25_ms": 2.0, "knn_ms": 3.0,
                        "fuse_ms": 0.1, "rerank_ms": 0.0, "total_ms": 5.0})
        return [HYBRID_RESULT]

    with patch("backend.main.hybrid_search", side_effect=fake_search):
        response = client.post("/search", json={"query": "guide", "debug": True})
    data = response.json()
    item = data["results"][0]
    assert item["bm25_rank"] == 2
    assert item["knn_rank"] is None
    assert item["fused_score"] == 0.016
    assert data["timings"]["total_ms"] == 5.0


# ---- summarize ----------------------------------------------------------------

def test_summarize_requires_fields(client):
    assert client.post("/summarize", json={"query": "", "id": "x"}).status_code == 400
    assert client.post("/summarize", json={"query": "q", "id": ""}).status_code == 400


def test_summarize_own_page(client, solr):
    solr.get_chunks_by_page_id.return_value = [{"text": "Page body about AI."}]
    with patch("backend.main.is_gemini_available", return_value=True), \
         patch("backend.main.summarize", return_value="A short summary."):
        response = client.post("/summarize", json={"query": "What is AI?", "id": PAGE_ID})
    assert response.status_code == 200
    assert response.json() == {"id": PAGE_ID, "summary": "A short summary."}
    solr.get_chunks_by_page_id.assert_called_once_with(PAGE_ID, USER)


def test_summarize_foreign_page_is_404(client, solr):
    solr.get_chunks_by_page_id.return_value = []
    with patch("backend.main.is_gemini_available", return_value=True):
        response = client.post("/summarize", json={"query": "q", "id": PAGE_ID})
    assert response.status_code == 404


# ---- /me ----------------------------------------------------------------------

def test_export_downloads_full_text_per_page(client, solr):
    solr.scan.return_value = iter([
        {"page_id": "p1", "url": "https://a.com/", "title": "A", "timestamp": "2024-02-01T00:00:00Z",
         "text": "Second part here.", "chunk_id": 1},
        {"page_id": "p1", "url": "https://a.com/", "title": "A", "timestamp": "2024-02-01T00:00:00Z",
         "text": "First part.", "chunk_id": 0},
        {"page_id": "p2", "url": "https://b.com/", "title": "B", "timestamp": "2024-01-01T00:00:00Z",
         "text": "Only part.", "chunk_id": 0},
    ])
    response = client.get("/me/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    pages = response.json()["pages"]
    assert pages == [
        {"url": "https://a.com/", "title": "A", "timestamp": "2024-02-01T00:00:00Z",
         "text": "First part.\n\nSecond part here."},
        {"url": "https://b.com/", "title": "B", "timestamp": "2024-01-01T00:00:00Z", "text": "Only part."},
    ]
    assert solr.scan.call_args[0][1] == USER


def test_delete_all_my_data(client, solr):
    response = client.delete("/me/data")
    assert response.status_code == 204
    solr.delete_user.assert_called_once_with(USER)


# ---- cross-cutting --------------------------------------------------------------

def test_rate_limit_returns_json_429(client):
    for _ in range(20):
        assert client.post("/summarize", json={"query": "", "id": "x"}).status_code == 400
    response = client.post("/summarize", json={"query": "", "id": "x"})
    assert response.status_code == 429
    assert "detail" in response.json()


def test_cors_allows_only_configured_origins(client):
    allowed = client.options("/search", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
    })
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    denied = client.options("/search", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST",
    })
    assert "access-control-allow-origin" not in denied.headers


def test_startup_fails_without_cognito_config():
    with patch("backend.auth.COGNITO_USER_POOL_ID", ""), patch("backend.main.get_model"):
        with pytest.raises(RuntimeError, match="COGNITO_USER_POOL_ID"):
            with TestClient(app):
                pass
