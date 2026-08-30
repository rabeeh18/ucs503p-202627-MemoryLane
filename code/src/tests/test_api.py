from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
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


def test_memory_requires_fields(client):
    response = client.post("/memory", json={"url": "", "title": "t", "content": "c"})
    assert response.status_code == 400

    response = client.post("/memory", json={"url": "https://ex.com", "title": "", "content": "c"})
    assert response.status_code == 400

    response = client.post("/memory", json={"url": "https://ex.com", "title": "t", "content": ""})
    assert response.status_code == 400


def test_memory_success_indexes_chunks(client):
    mock_solr = MagicMock()
    with patch("backend.main.get_solr_client", return_value=mock_solr), \
         patch("backend.main.chunk_text", return_value=["chunk-a", "chunk-b"]), \
         patch("backend.main.get_embeddings", return_value=[[0.1] * 384, [0.2] * 384]):
        response = client.post("/memory", json={
            "url": "https://www.example.com/guide?utm_source=x",
            "title": "Guide",
            "content": "hello world",
        })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["metadata"]["chunks"] == 2
    assert data["metadata"]["url"] == "https://example.com/guide"
    mock_solr.delete_by_query.assert_called_once()
    mock_solr.add_documents.assert_called_once()
    docs = mock_solr.add_documents.call_args[0][0]
    assert docs[0]["id"].endswith("::chunk::0")
    assert docs[1]["id"].endswith("::chunk::1")


def test_search_requires_query(client):
    response = client.post("/search", json={"query": "   "})
    assert response.status_code == 400


def test_search_without_gemini_omits_summary(client):
    hybrid_results = [{
        "rank": 1,
        "webpage_id": "example.com_guide",
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


def test_search_debug_includes_scores(client):
    hybrid_results = [{
        "rank": 1,
        "webpage_id": "example.com_guide",
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
        response = client.post("/search", json={"query": "guide", "debug": True, "summarize": False})
    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["bm25_score"] == 0.8
    assert item["vector_score"] == 0.6
    assert item["fused_score"] == 0.7


def test_summarize_requires_fields(client):
    response = client.post("/summarize", json={"query": "", "id": "x"})
    assert response.status_code == 400
    response = client.post("/summarize", json={"query": "q", "id": ""})
    assert response.status_code == 400


def test_summarize_one_webpage(client):
    mock_solr = MagicMock()
    mock_solr.get_chunks_by_webpage_id.return_value = [{"text": "Page body about AI."}]
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
    mock_solr.get_chunks_by_webpage_id.assert_called_once_with(
        "en.wikipedia.org_wiki_Artificial_intelligence"
    )


def test_search_still_skips_summary_when_disabled(client):
    hybrid_results = [{
        "rank": 1,
        "webpage_id": "example.com_guide",
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
