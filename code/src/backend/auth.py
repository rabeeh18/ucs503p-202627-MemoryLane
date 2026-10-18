"""Cognito access-token verification.

Every endpoint except /health depends on current_user_id(). The user id is the
verified token's `sub` and is the only source of a user id anywhere in the API.
There is no bypass flag; tests use app.dependency_overrides.
"""
import logging
import threading

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import COGNITO_APP_CLIENT_ID, COGNITO_REGION, COGNITO_USER_POOL_ID
from backend.solr_client import is_valid_user_id

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
_jwks_client = None
_jwks_lock = threading.Lock()


def issuer() -> str:
    return f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"


def check_config() -> None:
    """Fail fast at startup when Cognito isn't configured."""
    missing = [
        name for name, value in (
            ("COGNITO_REGION", COGNITO_REGION),
            ("COGNITO_USER_POOL_ID", COGNITO_USER_POOL_ID),
            ("COGNITO_APP_CLIENT_ID", COGNITO_APP_CLIENT_ID),
        ) if not value
    ]
    if missing:
        raise RuntimeError(
            f"Cognito is not configured: set {', '.join(missing)} in .env "
            "(see .env.example). The API does not run without authentication."
        )


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        with _jwks_lock:
            if _jwks_client is None:
                _jwks_client = jwt.PyJWKClient(
                    f"{issuer()}/.well-known/jwks.json", cache_keys=True, lifespan=3600,
                )
    return _jwks_client


class InvalidToken(Exception):
    pass


def verify_access_token(token: str) -> str:
    """Verify a Cognito access token and return its `sub`. Raises InvalidToken."""
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer(),
            # Cognito access tokens have no `aud`; client_id is checked below.
            options={"verify_aud": False, "require": ["exp", "iss", "sub", "token_use", "client_id"]},
        )
    except Exception as e:
        raise InvalidToken(type(e).__name__) from None

    if claims.get("token_use") != "access":
        raise InvalidToken("token_use")
    if claims.get("client_id") != COGNITO_APP_CLIENT_ID:
        raise InvalidToken("client_id")
    sub = claims.get("sub")
    if not isinstance(sub, str) or not is_valid_user_id(sub):
        raise InvalidToken("sub")
    return sub


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def current_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """FastAPI dependency: the signed-in user's id, or 401."""
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _unauthorized("Not signed in")
    try:
        user_id = verify_access_token(credentials.credentials)
    except InvalidToken as e:
        # Never log the token itself.
        logger.info(f"Rejected access token ({e})")
        raise _unauthorized("Invalid or expired token")
    request.state.user_id = user_id
    return user_id
