"""The server side of local-first storage: device keys, settings, moving pages
between the extension and the server, summaries of local pages, encrypted backups."""
import base64
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend import config, device_data
from backend.auth import current_user_id
from backend.chunking import chunk_text
from backend.ingest import ingest_page
from backend.main import app, limiter
from backend.url_utils import generate_page_id, normalize_url

USER = "user-local"
OTHER = "user-other"
TEXT = ("Sourdough starter needs flour and water fed daily. " * 12 + "\n\n") * 3


@pytest.fixture(autouse=True)
def device_store(tmp_path):
    device_data.reset_for_tests(str(tmp_path / "device.db"), str(tmp_path / "backups"))
    yield
    device_data.reset_for_tests(str(tmp_path / "device2.db"), str(tmp_path / "backups2"))


@pytest.fixture
def solr():
    mock = MagicMock()
    mock.get_page_head.return_value = None
    mock.count_pages.return_value = 0
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


# ---- settings and identity -------------------------------------------------------

def test_search_settings_are_public_and_match_config(client):
    app.dependency_overrides.clear()
    data = client.get("/search-settings").json()
    assert data["RRF_K"] == config.RRF_K
    assert data["MIN_VECTOR_SIMILARITY"] == config.MIN_VECTOR_SIMILARITY
    assert data["EMBEDDING_QUERY_PREFIX"] == config.EMBEDDING_QUERY_PREFIX


def test_me_returns_library_and_a_stable_device_key(client):
    first = client.get("/me").json()
    second = client.get("/me").json()
    assert first["library_id"] == USER
    assert first["device_key"] == second["device_key"]
    assert len(base64.urlsafe_b64decode(first["device_key"] + "==")) == 32


def test_device_keys_differ_per_library():
    assert device_data.device_key(USER) != device_data.device_key(OTHER)


def test_deleting_my_data_forgets_key_and_backup(client, solr):
    key = client.get("/me").json()["device_key"]
    client.put("/backup", content=b"opaque")
    assert client.delete("/me/data").status_code == 204
    assert client.get("/backup/info").status_code == 404
    assert client.get("/me").json()["device_key"] != key


# ---- moving pages --------------------------------------------------------------------

def test_transfer_keeps_text_title_description_and_time(client, solr):
    with patch("backend.ingest.embed_passages", side_effect=_fake_embed):
        response = client.post("/memory/transfer", json={
            "url": "https://example.com/bread", "title": "Bread", "chunks": chunk_text(TEXT),
            "description": "How to keep a starter.", "timestamp": "2026-03-04T05:06:07.123Z",
            "content_hash": "a" * 64,
        })
    assert response.status_code == 200
    docs = solr.upsert_page_chunks.call_args.args[1]
    assert [d["text"] for d in docs] == chunk_text(TEXT)
    assert docs[0]["timestamp"] == "2026-03-04T05:06:07.123Z"
    assert docs[0]["description"] == "How to keep a starter."
    assert docs[0]["page_id"] == generate_page_id(USER, normalize_url("https://example.com/bread"))
    assert docs[0]["content_hash"] == "a" * 64


def test_prepared_chunks_are_stored_as_they_are(solr):
    # A YouTube page's text has single-word lines ("Transcript:") cleaning would drop.
    chunks = ["Title: Talk\nChannel: Someone\n\nTranscript:\n" + "words of the talk " * 30]
    with patch("backend.ingest.embed_passages", side_effect=_fake_embed):
        ingest_page(USER, "https://www.youtube.com/watch?v=abcdefghijk", "Talk", "",
                    prepared_chunks=chunks, fetch_youtube=False, solr=solr, description="")
    docs = solr.upsert_page_chunks.call_args.args[1]
    assert [d["text"] for d in docs] == chunks


def test_page_content_returns_the_chunks(client, solr):
    page_id = generate_page_id(USER, "https://example.com/bread")
    chunks = chunk_text(TEXT)
    solr.get_page_head.return_value = {"page_id": page_id}
    solr.get_chunks_by_page_id.return_value = [
        {"url": "https://example.com/bread", "title": "Bread", "description": "d",
         "timestamp": "2026-01-01T00:00:00Z", "text": c} for c in chunks
    ]
    data = client.get(f"/memory/{page_id}/content").json()
    assert data["title"] == "Bread"
    assert data["chunks"] == chunks


def test_page_content_of_someone_elses_page_is_404(client, solr):
    solr.get_page_head.return_value = None
    assert client.get("/memory/0123456789abcdef0123456789abcdef/content").status_code == 404


# ---- summaries of local pages -----------------------------------------------------

def test_summarize_text_uses_the_sent_text(client):
    with patch("backend.main.is_gemini_available", return_value=True), \
         patch("backend.main.summarize", return_value="A summary.") as summarize:
        response = client.post("/summarize/text", json={"query": "starter", "text": TEXT})
    assert response.json()["summary"] == "A summary."
    assert summarize.call_args.args[1] == TEXT


def test_summarize_text_needs_sign_in(client):
    app.dependency_overrides.clear()
    assert client.post("/summarize/text", json={"query": "q", "text": "t"}).status_code == 401


# ---- encrypted backups -----------------------------------------------------------

def test_backup_round_trip_and_owner_scoping(client):
    blob = bytes(range(256)) * 10
    assert client.put("/backup", content=blob).status_code == 200
    assert client.get("/backup").content == blob
    assert client.get("/backup/info").json()["bytes"] == len(blob)
    app.dependency_overrides[current_user_id] = lambda: OTHER
    assert client.get("/backup").status_code == 404


def test_backup_size_limit(client):
    with patch.object(device_data, "MAX_BACKUP_BYTES", 100):
        assert client.put("/backup", content=b"x" * 101).status_code == 413


def test_empty_backup_is_refused(client):
    assert client.put("/backup", content=b"").status_code == 400


def test_delete_backup(client):
    client.put("/backup", content=b"opaque")
    assert client.delete("/backup").status_code == 204
    assert client.get("/backup/info").status_code == 404
