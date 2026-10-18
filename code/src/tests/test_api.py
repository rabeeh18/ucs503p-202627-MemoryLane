from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app, limiter


@pytest.fixture
def client():
    limiter.reset()
    with patch("backend.main.get_model"):
        with TestClient(app) as test_client:
            yield test_client


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


LONG_TEXT = "hello world " * 40


def _ingest_solr(head=None):
    solr = MagicMock()
    solr.get_page_head.return_value = head
    return solr


def _fake_embed(texts):
    return [[0.1] * 384 for _ in texts]


def test_memory_requires_fields(client):
    # Missing URL
    response = client.post("/memory", json={"url": "", "title": "t", "content": "c" * 250})
    assert response.status_code == 400

    # Too little readable text
    with patch("backend.ingest.get_solr_client", return_value=_ingest_solr()):
        response = client.post("/memory", json={"url": "https://ex.com", "title": "t", "content": "too short"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Not enough readable text on this page"

    # Empty title should fallback to domain
    with patch("backend.ingest.get_solr_client", return_value=_ingest_solr()), \
         patch("backend.ingest.embed_passages", side_effect=_fake_embed):
        response = client.post("/memory", json={"url": "https://ex.com/page", "title": "", "content": LONG_TEXT})
        assert response.status_code == 200
        assert response.json()["metadata"]["title"] == "ex.com"


def test_memory_success_indexes_chunks_for_legacy_user(client):
    mock_solr = _ingest_solr()
    with patch("backend.ingest.get_solr_client", return_value=mock_solr), \
         patch("backend.ingest.embed_passages", side_effect=_fake_embed):
        response = client.post("/memory", json={
            "url": "https://www.example.com/guide?utm_source=x",
            "title": "Guide",
            "content": LONG_TEXT,
            "html": "<html><body>tiny</body></html>",
        })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "saved"
    assert data["metadata"]["url"] == "https://example.com/guide"
    mock_solr.upsert_page_chunks.assert_called_once()
    page_id, docs = mock_solr.upsert_page_chunks.call_args[0]
    assert page_id == data["metadata"]["id"]
    assert data["metadata"]["chunks"] == len(docs)
    assert docs[0]["id"] == f"{page_id}::0"
    assert docs[0]["user_id"] == "legacy"
    assert docs[0]["url"] == "https://example.com/guide"


def test_memory_unchanged_page_is_not_reindexed(client):
    import hashlib
    from backend.cleaning import clean_content
    from backend.config import EMBEDDING_MODEL
    head = {
        "url": "https://example.com/guide",
        "title": "Guide",
        "total_chunks": 2,
        "timestamp": "2024-01-01T00:00:00Z",
        "content_hash": hashlib.sha256(clean_content(None, LONG_TEXT).encode()).hexdigest(),
        "embedding_model": EMBEDDING_MODEL,
    }
    mock_solr = _ingest_solr(head)
    with patch("backend.ingest.get_solr_client", return_value=mock_solr), \
         patch("backend.ingest.embed_passages") as mock_embed:
        response = client.post("/memory", json={
            "url": "https://example.com/guide/#section?utm_campaign=x",
            "title": "Guide again",
            "content": LONG_TEXT,
        })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unchanged"
    assert data["message"] == "Memory already stored"
    assert data["metadata"]["url"] == "https://example.com/guide"
    assert data["metadata"]["chunks"] == 2
    mock_embed.assert_not_called()
    mock_solr.upsert_page_chunks.assert_not_called()


def test_memory_youtube_ingestion(client):
    mock_solr = _ingest_solr()
    content = "Title: YT Video\nChannel: Channel\nDuration: 300 seconds\nSource: YouTube\n\nhello world"

    with patch("backend.ingest.get_solr_client", return_value=mock_solr), \
         patch("backend.ingest.process_youtube_video", return_value=(content, "YT Video", None)) as mock_yt, \
         patch("backend.ingest.embed_passages", side_effect=_fake_embed):
        response = client.post("/memory", json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "title": "dummy",
            "content": "dummy",  # YouTube doesn't need page content
            "is_manual": False
        })

    assert response.status_code == 200
    mock_yt.assert_called_once_with("https://www.youtube.com/watch?v=dQw4w9WgXcQ", False)
    docs = mock_solr.upsert_page_chunks.call_args[0][1]
    assert "Source: YouTube" in docs[0]["text"]
    assert "hello world" in docs[0]["text"]
    assert docs[0]["title"] == "YT Video"


def test_memory_youtube_skip_message_is_returned(client):
    mock_solr = _ingest_solr()
    with patch("backend.ingest.get_solr_client", return_value=mock_solr), \
         patch("backend.ingest.process_youtube_video",
               return_value=(None, None, "Skipped: YouTube video is over 2 hours long")):
        response = client.post("/memory", json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": "x", "content": "x",
        })
    assert response.status_code == 200
    assert response.json()["status"] == "skipped"
    assert response.json()["message"] == "Skipped: YouTube video is over 2 hours long"
    mock_solr.upsert_page_chunks.assert_not_called()


def test_memory_lookalike_youtube_host_is_not_treated_as_youtube(client):
    mock_solr = _ingest_solr()
    with patch("backend.ingest.get_solr_client", return_value=mock_solr), \
         patch("backend.ingest.process_youtube_video") as mock_yt, \
         patch("backend.ingest.embed_passages", side_effect=_fake_embed):
        response = client.post("/memory", json={
            "url": "https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
            "title": "t", "content": LONG_TEXT,
        })
    assert response.status_code == 200
    mock_yt.assert_not_called()


def test_memory_input_limits(client):
    too_long_url = "https://example.com/" + "a" * 2048
    assert client.post("/memory", json={"url": too_long_url, "title": "t", "content": "c"}).status_code == 422
    assert client.post("/memory", json={"url": "https://e.com", "title": "t" * 501, "content": "c"}).status_code == 422
    assert client.post("/memory", json={"url": "https://e.com", "title": "t", "content": "c" * 500_001}).status_code == 422
    assert client.post("/memory", json={"url": "https://e.com", "title": "t", "content": "c",
                                        "html": "h" * 3_000_001}).status_code == 422
    assert client.post("/search", json={"query": "q" * 501}).status_code == 422


def test_search_summarize_defaults_off(client):
    hybrid_results = [{
        "rank": 1, "page_id": "p", "title": "T", "url": "https://e.com/", "domain": "e.com",
        "timestamp": "t", "snippet": None,
    }]
    with patch("backend.main.hybrid_search", return_value=hybrid_results), \
         patch("backend.main._summary_for_webpage") as mock_sum:
        response = client.post("/search", json={"query": "guide"})
    assert response.status_code == 200
    mock_sum.assert_not_called()


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


def test_search_requires_query(client):
    response = client.post("/search", json={"query": "   "})
    assert response.status_code == 400


def test_search_without_gemini_omits_summary(client):
    hybrid_results = [{
        "rank": 1,
        "page_id": "example.com_guide",
        "title": "Guide",
        "url": "https://example.com/guide",
        "domain": "example.com",
        "timestamp": "2024-01-01T00:00:00Z",
        "bm25_score": 0.8,
        "vector_score": 0.6,
        "fused_score": 0.7,
    }]
    with patch("backend.main.hybrid_search", return_value=hybrid_results), \
         patch("backend.main.is_gemini_available", return_value=False):
        response = client.post("/search", json={
            "query": "how does the guide work",
            "summarize": True,
            "debug": False,
        })
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "how does the guide work"
    assert len(data["results"]) == 1
    assert data["results"][0]["summary"] is None
    assert data["results"][0]["title"] == "Guide"


def test_search_debug_includes_ranks_and_timings(client):
    hybrid_results = [{
        "rank": 1,
        "page_id": "example.com_guide",
        "title": "Guide",
        "url": "https://example.com/guide",
        "domain": "example.com",
        "timestamp": "2024-01-01T00:00:00Z",
        "snippet": "The guide explains things.",
        "bm25_rank": 2,
        "knn_rank": None,
        "fused_score": 0.016,
    }]

    def fake_search(query, top_k=None, timings=None):
        timings.update({"embed_ms": 1.0, "bm25_ms": 2.0, "knn_ms": 3.0,
                        "fuse_ms": 0.1, "rerank_ms": 0.0, "total_ms": 5.0})
        return hybrid_results

    with patch("backend.main.hybrid_search", side_effect=fake_search), \
         patch("backend.main.is_gemini_available", return_value=False):
        response = client.post("/search", json={"query": "guide", "debug": True, "summarize": False})
    assert response.status_code == 200
    data = response.json()
    item = data["results"][0]
    assert item["bm25_rank"] == 2
    assert item["knn_rank"] is None
    assert item["fused_score"] == 0.016
    assert item["snippet"] == "The guide explains things."
    assert data["timings"]["total_ms"] == 5.0
    assert set(data["timings"]) == {"embed_ms", "bm25_ms", "knn_ms", "fuse_ms", "rerank_ms", "total_ms"}


def test_search_non_debug_has_snippet_but_no_ranks(client):
    hybrid_results = [{
        "rank": 1,
        "page_id": "example.com_guide",
        "title": "Guide",
        "url": "https://example.com/guide",
        "domain": "example.com",
        "timestamp": "2024-01-01T00:00:00Z",
        "snippet": "The guide explains things.",
        "bm25_rank": 1,
        "knn_rank": 1,
        "fused_score": 0.03,
    }]
    with patch("backend.main.hybrid_search", return_value=hybrid_results):
        response = client.post("/search", json={"query": "guide", "summarize": False})
    data = response.json()
    item = data["results"][0]
    assert item["snippet"] == "The guide explains things."
    assert "bm25_rank" not in item
    assert data["timings"] is None


def test_summarize_requires_fields(client):
    response = client.post("/summarize", json={"query": "", "id": "x"})
    assert response.status_code == 400
    response = client.post("/summarize", json={"query": "q", "id": ""})
    assert response.status_code == 400


def test_summarize_one_webpage(client):
    mock_solr = MagicMock()
    mock_solr.get_chunks_by_page_id.return_value = [{"text": "Page body about AI."}]
    with patch("backend.main.get_solr_client", return_value=mock_solr), \
         patch("backend.main.is_gemini_available", return_value=True), \
         patch("backend.main.summarize", return_value="A short summary."):
        response = client.post("/summarize", json={
            "query": "What is artificial intelligence?",
            "id": "en.wikipedia.org_wiki_Artificial_intelligence",
        })
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "en.wikipedia.org_wiki_Artificial_intelligence"
    assert data["summary"] == "A short summary."
    mock_solr.get_chunks_by_page_id.assert_called_once_with(
        "en.wikipedia.org_wiki_Artificial_intelligence"
    )


def test_search_still_skips_summary_when_disabled(client):
    hybrid_results = [{
        "rank": 1,
        "page_id": "example.com_guide",
        "title": "Guide",
        "url": "https://example.com/guide",
        "domain": "example.com",
        "timestamp": "2024-01-01T00:00:00Z",
    }]
    with patch("backend.main.hybrid_search", return_value=hybrid_results), \
         patch("backend.main._summary_for_webpage") as mock_sum:
        response = client.post("/search", json={"query": "guide", "summarize": False})
    assert response.status_code == 200
    assert response.json()["results"][0]["summary"] is None
    mock_sum.assert_not_called()
