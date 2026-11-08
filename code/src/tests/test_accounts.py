"""Google and email + password sign-ins with the same verified email share a library."""
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from backend import accounts

EMAIL_SUB = "11111111-1111-1111-1111-111111111111"
GOOGLE_SUB = "22222222-2222-2222-2222-222222222222"
ATTACKER_SUB = "33333333-3333-3333-3333-333333333333"
GOOGLE_IDENTITY = json.dumps([{"providerName": "Google", "providerType": "Google", "userId": "1"}])


@pytest.fixture(autouse=True)
def linking_on(monkeypatch):
    monkeypatch.setattr(accounts, "COGNITO_DOMAIN", "https://auth.example.com")
    accounts.reset_for_tests()
    yield
    accounts.reset_for_tests()


def _people(**by_sub):
    """Fake userInfo: token "tok-<sub>" belongs to <sub>, with the given attributes."""
    calls = []

    def fetch(token):
        sub = token.removeprefix("tok-")
        calls.append(sub)
        return {"sub": sub, **by_sub[sub]}

    return patch.object(accounts, "fetch_userinfo", side_effect=fetch), calls


def _library(sub):
    return accounts.library_for(sub, f"tok-{sub}")


def test_email_first_then_google_share_a_library():
    people, _ = _people(**{
        EMAIL_SUB: {"email": "Ana@Example.com", "email_verified": "true"},
        GOOGLE_SUB: {"email": "ana@example.com", "email_verified": "true", "identities": GOOGLE_IDENTITY},
    })
    with people:
        assert _library(EMAIL_SUB) == EMAIL_SUB
        assert _library(GOOGLE_SUB) == EMAIL_SUB


def test_google_first_then_email_share_a_library():
    people, _ = _people(**{
        GOOGLE_SUB: {"email": "ana@example.com", "identities": GOOGLE_IDENTITY},
        EMAIL_SUB: {"email": "ana@example.com", "email_verified": "true"},
    })
    with people:
        assert _library(GOOGLE_SUB) == GOOGLE_SUB
        assert _library(EMAIL_SUB) == GOOGLE_SUB


def test_unverified_email_never_reaches_someone_elses_library():
    people, _ = _people(**{
        GOOGLE_SUB: {"email": "ana@example.com", "identities": GOOGLE_IDENTITY},
        ATTACKER_SUB: {"email": "ana@example.com", "email_verified": "false"},
    })
    with people:
        assert _library(GOOGLE_SUB) == GOOGLE_SUB
        assert _library(ATTACKER_SUB) == ATTACKER_SUB


def test_unverified_sign_in_first_does_not_claim_the_address():
    people, _ = _people(**{
        ATTACKER_SUB: {"email": "ana@example.com", "email_verified": "false"},
        GOOGLE_SUB: {"email": "ana@example.com", "identities": GOOGLE_IDENTITY},
    })
    with people:
        assert _library(ATTACKER_SUB) == ATTACKER_SUB
        assert _library(GOOGLE_SUB) == GOOGLE_SUB


@pytest.mark.parametrize("flag", ["false", "False", False, None, "", "yes", 1])
def test_only_a_true_verified_flag_counts(flag):
    assert accounts.verified_email({"email": "a@b.com", "email_verified": flag}) is None


@pytest.mark.parametrize("flag", ["true", "TRUE", True])
def test_true_verified_flag_counts(flag):
    assert accounts.verified_email({"email": " A@B.com ", "email_verified": flag}) == "a@b.com"


def test_google_identity_counts_as_verified_but_other_providers_do_not():
    assert accounts.verified_email({"email": "a@b.com", "identities": GOOGLE_IDENTITY}) == "a@b.com"
    other = json.dumps([{"providerType": "SAML", "providerName": "Google"}])
    assert accounts.verified_email({"email": "a@b.com", "identities": other}) is None
    assert accounts.verified_email({"email": "a@b.com", "identities": "not json"}) is None
    assert accounts.verified_email({"email": "a@b.com", "username": "google_123"}) is None


def test_missing_or_odd_email_is_not_linked():
    assert accounts.verified_email({"email_verified": "true"}) is None
    assert accounts.verified_email({"email": "nope", "email_verified": "true"}) is None
    assert accounts.verified_email({"email": ["a@b.com"], "email_verified": "true"}) is None


def test_known_sign_in_does_not_ask_cognito_again():
    people, calls = _people(**{EMAIL_SUB: {"email": "a@b.com", "email_verified": "true"}})
    with people:
        _library(EMAIL_SUB)
        _library(EMAIL_SUB)
        accounts._linked.clear()  # survives a restart: read back from the database
        assert _library(EMAIL_SUB) == EMAIL_SUB
    assert calls == [EMAIL_SUB]


def test_unverified_is_rechecked_later_and_then_links(monkeypatch):
    info = {"email": "ana@example.com", "email_verified": "false"}
    people, calls = _people(**{
        GOOGLE_SUB: {"email": "ana@example.com", "identities": GOOGLE_IDENTITY},
        EMAIL_SUB: info,
    })
    with people:
        _library(GOOGLE_SUB)
        assert _library(EMAIL_SUB) == EMAIL_SUB
        assert _library(EMAIL_SUB) == EMAIL_SUB          # cached for a few minutes
        assert calls.count(EMAIL_SUB) == 1
        info["email_verified"] = "true"
        monkeypatch.setattr(accounts, "UNVERIFIED_RECHECK_SECONDS", 0)
        assert _library(EMAIL_SUB) == GOOGLE_SUB


def test_cognito_failure_for_a_new_sign_in_is_an_error_and_stores_nothing():
    with patch.object(accounts, "fetch_userinfo", side_effect=accounts.LinkUnavailable("ConnectError")):
        with pytest.raises(accounts.LinkUnavailable):
            _library(EMAIL_SUB)
    people, _ = _people(**{EMAIL_SUB: {"email": "a@b.com", "email_verified": "true"}})
    with people:
        assert _library(EMAIL_SUB) == EMAIL_SUB


def test_userinfo_for_a_different_sub_is_refused():
    with patch.object(accounts, "fetch_userinfo",
                      return_value={"sub": GOOGLE_SUB, "email": "a@b.com", "email_verified": "true"}):
        with pytest.raises(accounts.LinkUnavailable):
            _library(EMAIL_SUB)


def test_delete_all_forgets_the_links():
    people, _ = _people(**{
        EMAIL_SUB: {"email": "a@b.com", "email_verified": "true"},
        GOOGLE_SUB: {"email": "a@b.com", "identities": GOOGLE_IDENTITY},
    })
    with people:
        _library(EMAIL_SUB)
        _library(GOOGLE_SUB)
        accounts.forget_library(EMAIL_SUB)
        assert _library(GOOGLE_SUB) == GOOGLE_SUB
        assert _library(EMAIL_SUB) == GOOGLE_SUB
    db = accounts._db()
    assert db.execute("SELECT COUNT(*) FROM libraries").fetchone()[0] == 1


def test_linking_off_without_a_cognito_domain(monkeypatch):
    monkeypatch.setattr(accounts, "COGNITO_DOMAIN", "")
    with patch.object(accounts, "fetch_userinfo") as fetch:
        assert _library(EMAIL_SUB) == EMAIL_SUB
    fetch.assert_not_called()


def test_fetch_userinfo_sends_the_users_own_token():
    response = MagicMock()
    response.json.return_value = {"sub": EMAIL_SUB}
    with patch.object(accounts.httpx, "get", return_value=response) as get:
        assert accounts.fetch_userinfo("abc") == {"sub": EMAIL_SUB}
    assert get.call_args.args[0] == "https://auth.example.com/oauth2/userInfo"
    assert get.call_args.kwargs["headers"] == {"Authorization": "Bearer abc"}


@pytest.mark.parametrize("problem", [
    httpx.ConnectError("down"),
    httpx.HTTPStatusError("401", request=httpx.Request("GET", "https://x"), response=httpx.Response(401)),
])
def test_fetch_userinfo_failures_become_link_unavailable(problem):
    with patch.object(accounts.httpx, "get", side_effect=problem):
        with pytest.raises(accounts.LinkUnavailable):
            accounts.fetch_userinfo("abc")


def test_fetch_userinfo_rejects_non_objects():
    response = MagicMock()
    response.json.return_value = ["sub"]
    with patch.object(accounts.httpx, "get", return_value=response):
        with pytest.raises(accounts.LinkUnavailable):
            accounts.fetch_userinfo("abc")
