"""Problem reports: stored before the API answers, emailed in the background,
retried with backoff, scoped to the user, and never trusting client-sent identity."""
import json
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend import accounts, reports
from backend.auth import current_user_id
from backend.main import app, limiter

USER = "user-report"
OTHER = "user-other"

EMAIL_ON = {
    "SMTP_HOST": "smtp.example.com",
    "REPORTS_FROM": "MemoryLane <reports@example.com>",
    "REPORTS_TO": "me@example.com",
}


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    reports.reset_for_tests()
    monkeypatch.setattr(reports, "REPORTS_DB", str(tmp_path / "reports.db"))
    monkeypatch.setattr(reports, "SMTP_HOST", "")
    yield
    reports.reset_for_tests()


@pytest.fixture
def email_on(monkeypatch):
    for name, value in EMAIL_ON.items():
        monkeypatch.setattr(reports, name, value)


@pytest.fixture
def client():
    limiter.reset()
    app.dependency_overrides[current_user_id] = lambda: USER
    with patch("backend.main.get_model"), patch.object(reports, "start_sender"):
        with TestClient(app) as test_client:
            yield test_client
    app.dependency_overrides.clear()


def _rows():
    return reports._db().execute(
        "SELECT user_id, email, message, context, sent_at, attempts FROM reports ORDER BY id"
    ).fetchall()


# ---- API -----------------------------------------------------------------------

def test_report_is_stored_before_the_reply(client):
    body = {
        "message": "Search shows Nintendo for football",
        "source": "web",
        "context": {"app_version": "1.0.0", "page": "/search", "user_agent": "Chrome", "last_error": ""},
    }
    with patch.object(accounts, "email_for", return_value="rabeeh@example.com"):
        response = client.post("/reports", json=body)
    assert response.status_code == 202
    assert response.json()["status"] == "received"
    [(user_id, email, message, context, sent_at, attempts)] = _rows()
    assert user_id == USER
    assert email == "rabeeh@example.com"
    assert message == "Search shows Nintendo for football"
    assert json.loads(context)["page"] == "/search"
    assert sent_at is None and attempts == 0


def test_page_query_strings_and_odd_paths_are_dropped(client):
    for page, stored in [("/search?q=my secret query", "/search"), ("/map#topic", "/map"),
                         ("https://evil.example/x", ""), ("/library", "/library")]:
        limiter.reset()
        client.post("/reports", json={"message": "x", "context": {"page": page}})
        assert json.loads(_rows()[-1][3])["page"] == stored


def test_identity_comes_from_the_token_not_the_body(client):
    body = {"message": "hi", "user_id": OTHER, "email": "someone@else.com", "context": {}}
    with patch.object(accounts, "email_for", return_value=None):
        assert client.post("/reports", json=body).status_code == 202
    [(user_id, email, *_)] = _rows()
    assert user_id == USER and email is None


@pytest.mark.parametrize("body", [
    {"message": ""},
    {"message": "x" * 4001},
    {"message": "x", "source": "email"},
    {"message": "x", "context": {"user_agent": "u" * 401}},
])
def test_invalid_reports_are_rejected(client, body):
    assert client.post("/reports", json=body).status_code == 422
    assert _rows() == []


def test_blank_message_after_cleaning_is_rejected(client):
    assert client.post("/reports", json={"message": " \x00\x01 "}).status_code == 400


def test_reports_are_rate_limited(client):
    codes = [client.post("/reports", json={"message": f"r{i}"}).status_code for i in range(6)]
    assert codes == [202] * 5 + [429]


def test_reports_need_sign_in():
    limiter.reset()
    with patch("backend.main.get_model"), patch.object(reports, "start_sender"):
        with TestClient(app) as anonymous:
            assert anonymous.post("/reports", json={"message": "x"}).status_code == 401


def test_delete_all_data_removes_only_my_reports(client):
    reports.save_report(OTHER, "theirs", {})
    client.post("/reports", json={"message": "mine"})
    with patch("backend.main.get_solr_client"):
        assert client.delete("/me/data").status_code == 204
    assert [row[0] for row in _rows()] == [OTHER]


def test_export_includes_my_reports_only(client):
    reports.save_report(OTHER, "theirs", {})
    client.post("/reports", json={"message": "mine", "context": {"page": "/library"}})
    with patch("backend.main.get_solr_client") as solr:
        solr.return_value.scan.return_value = []
        data = client.get("/me/export").json()
    assert [r["message"] for r in data["reports"]] == ["mine"]
    assert data["reports"][0]["context"]["page"] == "/library"


# ---- sending -------------------------------------------------------------------

def test_nothing_is_sent_when_email_is_off():
    reports.save_report(USER, "hello", {})
    with patch.object(reports, "send_email") as send:
        assert reports.send_due() == 0
    send.assert_not_called()


def test_due_reports_are_emailed_once(email_on):
    reports.save_report(USER, "Saving hangs\nmore detail", {"source": "extension", "app_version": "2.1.2"},
                        email="rabeeh@example.com")
    with patch.object(reports, "send_email") as send:
        assert reports.send_due() == 1
        assert reports.send_due() == 0
    msg = send.call_args.args[0]
    assert msg["To"] == "me@example.com"
    assert msg["Reply-To"] == "rabeeh@example.com"
    assert msg["Subject"].endswith("Saving hangs")
    body = msg.get_content()
    assert "more detail" in body and "Version: 2.1.2" in body and "App: extension" in body
    assert _rows()[0][4] is not None  # sent_at


def test_failed_send_is_retried_with_backoff(email_on):
    reports.save_report(USER, "x", {})
    now = time.time() + 1
    with patch.object(reports, "send_email", side_effect=OSError("connection refused")):
        assert reports.send_due(now=now) == 0
    row = reports._db().execute("SELECT attempts, next_try_at, last_error FROM reports").fetchone()
    assert row[0] == 1 and row[1] == now + 60 and "OSError" in row[2]
    with patch.object(reports, "send_email") as send:
        assert reports.send_due(now=now + 30) == 0  # not due yet
        assert reports.send_due(now=now + 61) == 1
    send.assert_called_once()


def test_retry_delay_grows_and_is_capped():
    assert [reports.retry_delay(n) for n in (1, 2, 3)] == [60, 120, 240]
    assert reports.retry_delay(50) == reports.RETRY_MAX_SECONDS


def test_gives_up_after_max_attempts(email_on):
    reports.save_report(USER, "x", {})
    reports._db().execute("UPDATE reports SET attempts = ?", (reports.MAX_ATTEMPTS,))
    with patch.object(reports, "send_email") as send:
        assert reports.send_due() == 0
    send.assert_not_called()


def test_unsent_reports_survive_a_restart(email_on):
    reports.save_report(USER, "before the crash", {})
    reports._conn.close()
    reports._conn = None  # a new process opens the same file
    with patch.object(reports, "send_email") as send:
        assert reports.send_due() == 1
    assert "before the crash" in send.call_args.args[0].get_content()


def test_subject_cannot_inject_headers(email_on):
    msg = reports.build_email(1, 0.0, USER, "a@b.com\r\nBcc: x@evil.com", "hi\r\nBcc: x@evil.com", {})
    assert "\n" not in msg["Subject"] and "\n" not in msg["Reply-To"]
    assert msg["Bcc"] is None


def test_message_text_is_never_logged(email_on, caplog):
    reports.save_report(USER, "my private words", {})
    with patch.object(reports, "send_email", side_effect=OSError("down")):
        reports.send_due()
    assert "my private words" not in caplog.text


def test_email_for_needs_linking(monkeypatch, tmp_path):
    monkeypatch.setattr(accounts, "COGNITO_DOMAIN", "")
    assert accounts.email_for("anyone") is None
