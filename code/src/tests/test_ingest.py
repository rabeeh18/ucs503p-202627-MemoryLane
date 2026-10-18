import hashlib
import re
from unittest.mock import MagicMock, patch

import pytest

from backend import ingest
from backend.ingest import IngestError, ingest_page, to_solr_date
from backend.url_utils import generate_page_id

TEXT = " ".join(f"word{i}" for i in range(120)) + "."


def _solr(head=None):
    solr = MagicMock()
    solr.get_page_head.return_value = head
    return solr


def _fake_embed(texts):
    return [[0.1] * 384 for _ in texts]


@pytest.fixture(autouse=True)
def fake_embeddings():
    with patch("backend.ingest.embed_passages", side_effect=_fake_embed) as mock_embed:
        yield mock_embed


def test_saves_chunks_with_v2_fields(fake_embeddings):
    solr = _solr()
    result = ingest_page("user-1", "https://www.example.com/a?utm_source=x", "Title", TEXT, solr=solr)

    assert result.status == "saved"
    assert result.url == "https://example.com/a"
    assert result.page_id == generate_page_id("user-1", "https://example.com/a")
    assert len(result.page_id) == 32
    page_id, docs = solr.upsert_page_chunks.call_args.args
    assert page_id == result.page_id
    assert result.chunks == len(docs) >= 1
    doc = docs[0]
    assert doc["id"] == f"{page_id}::0"
    assert doc["user_id"] == "user-1"
    assert doc["page_id"] == page_id
    assert doc["domain"] == "example.com"
    assert doc["content_hash"] == hashlib.sha256(TEXT.encode()).hexdigest()
    assert doc["embedding_model"] == ingest.EMBEDDING_MODEL
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", doc["timestamp"])
    assert "webpage_id" not in doc
    # Passages are embedded as title + chunk
    embedded = fake_embeddings.call_args.args[0]
    assert embedded[0] == f"Title\n\n{doc['text']}"


def test_same_url_different_users_get_different_pages():
    a = ingest_page("user-a", "https://example.com/a", "T", TEXT, solr=_solr())
    b = ingest_page("user-b", "https://example.com/a", "T", TEXT, solr=_solr())
    assert a.page_id != b.page_id


def test_unchanged_page_is_not_reindexed(fake_embeddings):
    head = {
        "url": "https://example.com/a", "title": "Old title", "domain": "example.com",
        "timestamp": "2024-01-01T00:00:00Z", "total_chunks": 2,
        "content_hash": hashlib.sha256(TEXT.encode()).hexdigest(),
        "embedding_model": ingest.EMBEDDING_MODEL,
    }
    solr = _solr(head)
    result = ingest_page("u", "https://example.com/a", "T", TEXT, solr=solr)
    assert result.status == "unchanged"
    assert result.chunks == 2
    assert result.timestamp == "2024-01-01T00:00:00Z"
    solr.upsert_page_chunks.assert_not_called()
    fake_embeddings.assert_not_called()


def test_changed_page_is_reingested():
    head = {"content_hash": "old", "embedding_model": ingest.EMBEDDING_MODEL}
    solr = _solr(head)
    assert ingest_page("u", "https://example.com/a", "T", TEXT, solr=solr).status == "saved"
    solr.upsert_page_chunks.assert_called_once()


def test_new_embedding_model_forces_reingest():
    head = {"content_hash": hashlib.sha256(TEXT.encode()).hexdigest(), "embedding_model": "other-model"}
    solr = _solr(head)
    assert ingest_page("u", "https://example.com/a", "T", TEXT, solr=solr).status == "saved"


def test_too_little_text_is_rejected_with_422():
    with pytest.raises(IngestError) as exc:
        ingest_page("u", "https://example.com/a", "T", "only a few words here", solr=_solr())
    assert exc.value.status_code == 422
    assert exc.value.detail == "Not enough readable text on this page"


def test_missing_url_is_rejected_with_400():
    with pytest.raises(IngestError) as exc:
        ingest_page("u", "  ", "T", TEXT, solr=_solr())
    assert exc.value.status_code == 400


def test_html_is_cleaned_before_chunking():
    solr = _solr()
    with patch("backend.ingest.clean_content", return_value=TEXT) as mock_clean:
        ingest_page("u", "https://example.com/a", "T", "fallback", html="<html/>", solr=solr)
    mock_clean.assert_called_once_with("<html/>", "fallback")


def test_untitled_falls_back_to_domain():
    result = ingest_page("u", "https://example.com/a", "Untitled", TEXT, solr=_solr())
    assert result.title == "example.com"


def test_canonical_url_resolution():
    result = ingest_page("u", "https://example.com/blog/post-1?utm=x", "T", TEXT,
                         canonical_url="/blog/post-1-canonical", solr=_solr())
    assert result.url == "https://example.com/blog/post-1-canonical"
    result = ingest_page("u", "https://example.com/blog/post-2?utm_source=x", "T", TEXT,
                         canonical_url="invalid://url", solr=_solr())
    assert result.url == "https://example.com/blog/post-2"


def test_youtube_transcript_skips_cleaning_and_word_minimum():
    solr = _solr()
    content = "Title: YT\nChannel: C\nDuration: 60 seconds\nSource: YouTube\n\nhello world"
    with patch("backend.ingest.process_youtube_video", return_value=(content, "YT", None)), \
         patch("backend.ingest.clean_content") as mock_clean:
        result = ingest_page("u", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "x", "x", solr=solr)
    mock_clean.assert_not_called()
    assert result.status == "saved"
    assert result.title == "YT"
    assert "hello world" in solr.upsert_page_chunks.call_args.args[1][0]["text"]


def test_youtube_skip_returns_skipped():
    solr = _solr()
    with patch("backend.ingest.process_youtube_video", return_value=(None, None, "Skipped: Shorts")):
        result = ingest_page("u", "https://www.youtube.com/shorts/dQw4w9WgXcQ", "x", "x", solr=solr)
    assert result.status == "skipped"
    assert result.message == "Skipped: Shorts"
    solr.upsert_page_chunks.assert_not_called()


def test_fetch_youtube_false_uses_given_text():
    with patch("backend.ingest.process_youtube_video") as mock_yt:
        result = ingest_page("u", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "Old", TEXT,
                             solr=_solr(), fetch_youtube=False)
    mock_yt.assert_not_called()
    assert result.status == "saved"


def test_timestamp_override_is_kept_in_utc():
    result = ingest_page("u", "https://example.com/a", "T", TEXT, solr=_solr(),
                         timestamp="2024-03-01T10:00:00+05:30")
    assert result.timestamp == "2024-03-01T04:30:00.000Z"


def test_to_solr_date_handles_z_and_bad_values():
    assert to_solr_date("2024-01-01T00:00:00Z") == "2024-01-01T00:00:00.000Z"
    assert re.fullmatch(r"\d{4}-.*Z", to_solr_date("not a date"))
    assert re.fullmatch(r"\d{4}-.*Z", to_solr_date(None))
