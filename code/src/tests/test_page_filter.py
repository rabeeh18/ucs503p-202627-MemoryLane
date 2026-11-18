"""The server's copy of the auto-capture rules (backend/page_filter.py)."""
import pytest

from unittest.mock import patch

from backend.page_filter import auto_capture_refusal, is_auto_capture_eligible


@pytest.mark.parametrize("url", [
    "https://mail.google.com/mail/u/0/#inbox",
    "https://outlook.live.com/mail/0/inbox",
    "https://mail.proton.me/u/0/inbox",
    "https://www.icloud.com/mail/",
    "https://webmail.example.com/?_task=mail",
    "https://intranet.example.com/owa/",
])
def test_email_pages_are_not_auto_captured(url):
    assert not is_auto_capture_eligible(url)


@pytest.mark.parametrize("url", [
    "https://en.wikipedia.org/wiki/Email",
    "https://docs.python.org/3/library/email.html",
])
def test_pages_about_email_still_pass(url):
    assert is_auto_capture_eligible(url)


@pytest.mark.parametrize("url", [
    "https://docs.google.com/document/d/1abc/edit",
    "https://www.icloud.com/photos/",
    "https://moodle.thapar.edu/course/view.php?id=4",
    "http://localhost:5173/library",
    "http://192.168.1.10/status",
    "https://example.com/account/settings",
    "https://example.com/invite?token=abc123",
])
def test_private_pages_are_not_auto_captured(url):
    assert not is_auto_capture_eligible(url)


def test_refusal_reads_the_page_html():
    article = "https://example.com/blog/post"
    assert auto_capture_refusal(article, "<p>An article</p>") is None
    # A hidden login form in an article's HTML is normal; the extension checks visible fields.
    assert auto_capture_refusal(article, '<div hidden><input type="password"></div><p>Story</p>') is None
    assert auto_capture_refusal(article, '<meta name="robots" content="noindex, nofollow">')
    assert auto_capture_refusal(article, '<meta content="index" name="robots">') is None
    assert auto_capture_refusal("https://mail.google.com/mail/u/0/#inbox", None)


# ---- the API refuses unsafe automatic saves, whatever the extension did --------

@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from backend.auth import current_user_id
    from backend.main import app, limiter
    limiter.reset()
    app.dependency_overrides[current_user_id] = lambda: "user-a"
    with patch("backend.main.get_model"), TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_api_skips_an_automatic_save_of_an_inbox(client):
    with patch("backend.main.ingest_page") as ingest:
        response = client.post("/memory", json={
            "url": "https://mail.google.com/mail/u/0/#inbox", "title": "Inbox (3,502)",
            "content": "x " * 300, "is_manual": False,
        })
    assert response.status_code == 200
    assert response.json()["status"] == "skipped"
    ingest.assert_not_called()


def test_api_skips_an_automatic_save_of_a_noindex_page(client):
    with patch("backend.main.ingest_page") as ingest:
        response = client.post("/memory", json={
            "url": "https://example.com/blog/post", "title": "Post", "content": "x " * 300,
            "html": '<head><meta name="robots" content="noindex"></head>', "is_manual": False,
        })
    assert response.json()["status"] == "skipped"
    ingest.assert_not_called()


def test_api_still_saves_the_same_page_by_hand(client):
    from backend.ingest import IngestResult
    result = IngestResult("saved", "ok", "a" * 32, "https://mail.google.com/mail/u/0/", "Inbox", "mail.google.com", "t", 1)
    with patch("backend.main.ingest_page", return_value=result) as ingest:
        response = client.post("/memory", json={
            "url": "https://mail.google.com/mail/u/0/#inbox", "title": "Inbox", "content": "x " * 300,
            "is_manual": True,
        })
    assert response.json()["status"] == "saved"
    ingest.assert_called_once()
