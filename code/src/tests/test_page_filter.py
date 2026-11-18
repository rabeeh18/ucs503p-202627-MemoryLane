"""The server's copy of the auto-capture rules (backend/page_filter.py)."""
import pytest

from backend.page_filter import is_auto_capture_eligible


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
    "https://www.icloud.com/photos/",
    "https://docs.python.org/3/library/email.html",
])
def test_pages_about_email_still_pass(url):
    assert is_auto_capture_eligible(url)
