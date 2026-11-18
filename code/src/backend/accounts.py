"""One library per verified email, whichever way the user signs in.

Cognito gives "Continue with Google" and email + password sign-ins different
`sub`s even for the same address. Pages are stored under a library id (the
`sub` of the first sign-in seen for that email), and every later sign-in whose
email is verified for the same address is pointed at that library.

The rules that keep this safe:
- The email comes from Cognito's userInfo endpoint, called with the user's own
  access token. Nothing the browser sends is trusted.
- Only a verified email links. `email_verified` must be true, or the sign-in
  must come from Google (Google only issues accounts for addresses it has
  verified). An unverified sign-in keeps its own library and claims nothing,
  so registering someone else's address gets you nowhere.
- Mappings are only stored once verified; an unverified answer is re-checked
  after a few minutes, so verifying later still links.
- If Cognito can't be reached for a sign-in seen for the first time, the
  request fails (503) instead of guessing, so pages never land in the wrong
  library.
- A sign-in that saved pages while unverified, and then links to an existing
  library, has those pages moved into it (backend/library_moves.py), so they
  aren't stranded under its old id.
- Known sign-ins are re-checked with Cognito once a day. If a sign-in's verified
  email has changed, or is no longer verified, the old address stops pointing at
  the library (unless another of its sign-ins still has it), so whoever verifies
  that address later can't reach this library.

The table lives in a small SQLite file (ACCOUNTS_DB). Without a Cognito domain
configured, linking is off and each sign-in is its own library.
"""
import json
import logging
import os
import sqlite3
import threading
import time

import httpx

from backend.config import ACCOUNTS_DB, COGNITO_DOMAIN
from backend.solr_client import is_valid_user_id

logger = logging.getLogger(__name__)

UNVERIFIED_RECHECK_SECONDS = 300
USERINFO_TIMEOUT_SECONDS = 5
# Known sign-ins are re-checked with Cognito this often (and retried after a failure).
REVALIDATE_SECONDS = 24 * 3600
REVALIDATE_RETRY_SECONDS = 600

_lock = threading.Lock()
_conn = None
_linked = {}        # sub -> (library id, email, last checked), for subs with a stored mapping
_unverified = {}    # sub -> time it was last found unverified
# Set when a library move is queued, so backend/library_moves.py starts it straight away.
moves_waiting = threading.Event()


class LinkUnavailable(Exception):
    """Cognito couldn't say who this is, and the sign-in isn't known yet."""


def enabled() -> bool:
    return bool(COGNITO_DOMAIN)


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        folder = os.path.dirname(ACCOUNTS_DB)
        if folder:
            os.makedirs(folder, exist_ok=True)
        conn = sqlite3.connect(ACCOUNTS_DB, check_same_thread=False, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS libraries ("
            " email TEXT PRIMARY KEY, library TEXT NOT NULL, created_at REAL NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sign_ins ("
            " sub TEXT PRIMARY KEY, library TEXT NOT NULL, email TEXT NOT NULL, created_at REAL NOT NULL)"
        )
        # Added later: when the sign-in's email was last checked with Cognito.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sign_ins)")}
        if "checked_at" not in columns:
            conn.execute("ALTER TABLE sign_ins ADD COLUMN checked_at REAL")
        # Pages saved under one library id that belong in another (see library_moves.py).
        conn.execute(
            "CREATE TABLE IF NOT EXISTS library_moves ("
            " old TEXT PRIMARY KEY, new TEXT NOT NULL, created_at REAL NOT NULL)"
        )
        conn.commit()
        _conn = conn
    return _conn


def _is_true(value) -> bool:
    # Cognito sends email_verified as the string "true" / "false".
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def _from_google(info: dict) -> bool:
    identities = info.get("identities")
    if isinstance(identities, str):
        try:
            identities = json.loads(identities)
        except ValueError:
            return False
    if not isinstance(identities, list):
        return False
    return any(
        isinstance(i, dict) and str(i.get("providerType", "")).lower() == "google"
        for i in identities
    )


def verified_email(info: dict) -> str | None:
    """The address to link on, or None if it isn't verified."""
    email = info.get("email")
    if not isinstance(email, str) or "@" not in email:
        return None
    if not (_is_true(info.get("email_verified")) or _from_google(info)):
        return None
    return email.strip().lower()


def fetch_userinfo(access_token: str) -> dict:
    """Ask Cognito who owns this access token. Raises LinkUnavailable."""
    try:
        response = httpx.get(
            f"{COGNITO_DOMAIN}/oauth2/userInfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=USERINFO_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        info = response.json()
    except Exception as e:
        raise LinkUnavailable(type(e).__name__) from None
    if not isinstance(info, dict):
        raise LinkUnavailable("not an object")
    return info


def _known(sub: str) -> tuple[str, str, float] | None:
    """(library, email, last checked) for a sign-in with a stored mapping."""
    known = _linked.get(sub)
    if known:
        return known
    with _lock:
        row = _db().execute(
            "SELECT library, email, COALESCE(checked_at, created_at) FROM sign_ins WHERE sub = ?", (sub,)
        ).fetchone()
    if row:
        _linked[sub] = (row[0], row[1], row[2])
        return _linked[sub]
    return None


def _revalidate(sub: str, access_token: str, library: str, email: str) -> None:
    """Re-check a known sign-in's email. If it changed or isn't verified any more,
    the old address stops vouching for this library. Never fails the request."""
    now = time.time()
    try:
        info = fetch_userinfo(access_token)
    except LinkUnavailable:
        _linked[sub] = (library, email, now - REVALIDATE_SECONDS + REVALIDATE_RETRY_SECONDS)
        return
    if info.get("sub") != sub:
        return
    current = verified_email(info)
    with _lock:
        db = _db()
        with db:
            if current != email:
                others = db.execute(
                    "SELECT COUNT(*) FROM sign_ins WHERE library = ? AND email = ? AND sub != ?",
                    (library, email, sub),
                ).fetchone()[0]
                if not others:
                    db.execute("DELETE FROM libraries WHERE email = ? AND library = ?", (email, library))
                if current:
                    db.execute(
                        "INSERT OR IGNORE INTO libraries (email, library, created_at) VALUES (?, ?, ?)",
                        (current, library, now),
                    )
                logger.info("A sign-in's verified email changed; its old address no longer links")
            db.execute(
                "UPDATE sign_ins SET email = ?, checked_at = ? WHERE sub = ?",
                (current or email, now, sub),
            )
    _linked[sub] = (library, current or email, now)


def library_for(sub: str, access_token: str) -> str:
    """The library id this verified sign-in uses. Raises LinkUnavailable."""
    if not enabled():
        return sub
    known = _known(sub)
    if known:
        library, email, checked = known
        if time.time() - (checked or 0) >= REVALIDATE_SECONDS:
            _revalidate(sub, access_token, library, email)
        return library
    checked = _unverified.get(sub)
    if checked and time.time() - checked < UNVERIFIED_RECHECK_SECONDS:
        return sub

    info = fetch_userinfo(access_token)
    if info.get("sub") != sub:
        raise LinkUnavailable("sub mismatch")
    email = verified_email(info)
    if email is None:
        _unverified[sub] = time.time()
        return sub

    now = time.time()
    with _lock:
        db = _db()
        with db:
            db.execute(
                "INSERT OR IGNORE INTO libraries (email, library, created_at) VALUES (?, ?, ?)",
                (email, sub, now),
            )
            library = db.execute("SELECT library FROM libraries WHERE email = ?", (email,)).fetchone()[0]
            db.execute(
                "INSERT OR IGNORE INTO sign_ins (sub, library, email, created_at, checked_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (sub, library, email, now, now),
            )
            library = db.execute("SELECT library FROM sign_ins WHERE sub = ?", (sub,)).fetchone()[0]
            if library != sub and is_valid_user_id(library):
                # Until now this sign-in used its own id as its library (while it was
                # unverified, or before linking existed). Any pages saved there move over.
                db.execute(
                    "INSERT OR IGNORE INTO library_moves (old, new, created_at) VALUES (?, ?, ?)",
                    (sub, library, now),
                )
    if not is_valid_user_id(library):
        raise LinkUnavailable("stored library id")
    _unverified.pop(sub, None)
    _linked[sub] = (library, email, now)
    if library != sub:
        logger.info("Sign-in linked to an existing library")
        moves_waiting.set()
    return library


def pending_moves() -> list[tuple[str, str]]:
    """Library moves still to do, oldest first: (old library, new library)."""
    if not enabled():
        return []
    with _lock:
        return [tuple(r) for r in _db().execute("SELECT old, new FROM library_moves ORDER BY created_at")]


def finish_move(old: str) -> None:
    with _lock:
        db = _db()
        with db:
            db.execute("DELETE FROM library_moves WHERE old = ?", (old,))


def moves_into(library: str) -> list[str]:
    """Old library ids whose pages are still being moved into `library`."""
    if not enabled():
        return []
    with _lock:
        return [r[0] for r in _db().execute("SELECT old FROM library_moves WHERE new = ?", (library,))]


def email_for(library: str) -> str | None:
    """The verified email of a library, or None (linking off, or not verified)."""
    if not enabled():
        return None
    with _lock:
        row = _db().execute("SELECT email FROM libraries WHERE library = ?", (library,)).fetchone()
    return row[0] if row else None


def forget_library(library: str) -> None:
    """Drop the stored email and sign-in links for a library (on "Delete all")."""
    if not enabled():
        return
    with _lock:
        db = _db()
        with db:
            db.execute("DELETE FROM sign_ins WHERE library = ?", (library,))
            db.execute("DELETE FROM libraries WHERE library = ?", (library,))
            db.execute("DELETE FROM library_moves WHERE new = ? OR old = ?", (library, library))
    for sub in [s for s, known in _linked.items() if known[0] == library]:
        _linked.pop(sub, None)


def reset_for_tests() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
        _linked.clear()
        _unverified.clear()
        moves_waiting.clear()
