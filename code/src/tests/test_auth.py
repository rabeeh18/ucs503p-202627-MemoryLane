import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from backend import auth
from backend.main import app, limiter

SUB = "4c1d6f2a-90b1-70e3-1a2b-3c4d5e6f7a8b"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(key=_KEY, **overrides):
    now = int(time.time())
    claims = {
        "sub": SUB,
        "iss": auth.issuer(),
        "client_id": auth.COGNITO_APP_CLIENT_ID,
        "token_use": "access",
        "scope": "openid email profile",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-kid"})


@pytest.fixture
def client():
    limiter.reset()
    app.dependency_overrides.clear()
    jwks = MagicMock()
    jwks.get_signing_key_from_jwt.return_value = SimpleNamespace(key=_KEY.public_key())
    solr = MagicMock()
    solr.list_pages.return_value = (0, [])
    with patch("backend.auth._get_jwks_client", return_value=jwks), \
         patch("backend.main.get_solr_client", return_value=solr), \
         patch("backend.main.get_model"):
        with TestClient(app) as test_client:
            test_client.solr = solr
            yield test_client


def _get(client, token=None, scheme="Bearer"):
    headers = {"Authorization": f"{scheme} {token}"} if token is not None else {}
    return client.get("/memories", headers=headers)


def _assert_401(response):
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_missing_token_is_401(client):
    _assert_401(_get(client))


def test_bad_signature_is_401(client):
    _assert_401(_get(client, _token(key=_OTHER_KEY)))


def test_expired_token_is_401(client):
    _assert_401(_get(client, _token(exp=int(time.time()) - 10)))


def test_id_token_is_401(client):
    _assert_401(_get(client, _token(token_use="id")))


def test_wrong_client_id_is_401(client):
    _assert_401(_get(client, _token(client_id="some-other-client")))


def test_wrong_issuer_is_401(client):
    _assert_401(_get(client, _token(iss="https://cognito-idp.us-east-1.amazonaws.com/other")))


def test_malformed_sub_is_401(client):
    _assert_401(_get(client, _token(sub="evil user:*")))


def test_missing_claims_are_401(client):
    _assert_401(_get(client, _token(client_id=None)))
    _assert_401(_get(client, _token(exp=None)))


def test_garbage_token_and_wrong_scheme_are_401(client):
    _assert_401(_get(client, "not-a-jwt"))
    _assert_401(_get(client, _token(), scheme="Basic"))


def test_hs256_token_is_rejected(client):
    forged = jwt.encode({"sub": SUB, "iss": auth.issuer(), "client_id": auth.COGNITO_APP_CLIENT_ID,
                         "token_use": "access", "exp": int(time.time()) + 60},
                        "secret", algorithm="HS256")
    _assert_401(_get(client, forged))


def test_valid_token_is_200_and_scopes_to_sub(client):
    response = _get(client, _token())
    assert response.status_code == 200
    client.solr.list_pages.assert_called_once_with(SUB, limit=20, offset=0)


def test_token_is_not_logged(client, caplog):
    token = _token(key=_OTHER_KEY)
    with caplog.at_level("DEBUG"):
        _get(client, token)
    assert token not in caplog.text


def test_issuer_and_jwks_url():
    assert auth.issuer() == "https://cognito-idp.ap-south-1.amazonaws.com/ap-south-1_TESTPOOL"
    auth._jwks_client = None
    try:
        assert auth._get_jwks_client().uri == f"{auth.issuer()}/.well-known/jwks.json"
    finally:
        auth._jwks_client = None


def test_check_config_names_missing_values():
    with patch("backend.auth.COGNITO_APP_CLIENT_ID", ""):
        with pytest.raises(RuntimeError, match="COGNITO_APP_CLIENT_ID"):
            auth.check_config()
