"""Problem reports from the website and the extension, emailed to the maintainer.

A report is written to SQLite (REPORTS_DB) before the API answers, so it is
never lost: if email isn't configured, or the mail server is down, it waits in
the table and a background sender retries it with backoff (also after a
restart). Sent reports stay in the table as a record; "Delete all my data"
removes a user's reports with everything else.

Email goes out over SMTP with STARTTLS (Amazon SES's SMTP interface in
production, any SMTP server locally). The credentials live only in the server's
.env; the browser never sees them. Without SMTP settings, reports are stored but
not sent.

What a report holds is exactly what the report form shows the user before they
send it: their message, the app and its version, the page they were on (path
only: no query string, so no search terms), the browser, and the last error
message. The sender's email comes from the server's own record of the sign-in
(accounts.py), never from the request.
"""
import json
import logging
import os
import re
import smtplib
import sqlite3
import threading
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from backend.config import (
    REPORTS_DB, REPORTS_FROM, REPORTS_TO, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER,
)

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 15
# Retry delays: 1 min, 2, 4, ... capped at 6 hours; give up after this many tries.
RETRY_BASE_SECONDS = 60
RETRY_MAX_SECONDS = 6 * 3600
MAX_ATTEMPTS = 12
# How often the sender looks for reports due a retry when nothing wakes it.
SWEEP_SECONDS = 60

_lock = threading.Lock()
_conn = None
_wake = threading.Event()
_stop = threading.Event()
_thread = None

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HEADER_UNSAFE = re.compile(r"[\r\n\x00-\x1f\x7f]+")


def email_enabled() -> bool:
    return bool(SMTP_HOST and REPORTS_TO and REPORTS_FROM)


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        folder = os.path.dirname(REPORTS_DB)
        if folder:
            os.makedirs(folder, exist_ok=True)
        conn = sqlite3.connect(REPORTS_DB, check_same_thread=False, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS reports ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " created_at REAL NOT NULL,"
            " user_id TEXT NOT NULL,"
            " email TEXT,"
            " message TEXT NOT NULL,"
            " context TEXT NOT NULL,"
            " sent_at REAL,"
            " attempts INTEGER NOT NULL DEFAULT 0,"
            " next_try_at REAL NOT NULL,"
            " last_error TEXT)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS reports_unsent ON reports (sent_at, next_try_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS reports_user ON reports (user_id)")
        conn.commit()
        _conn = conn
    return _conn


def clean_text(value: str | None, limit: int) -> str:
    """Control characters out (newlines and tabs kept), trimmed, capped."""
    return _CONTROL.sub("", value or "").strip()[:limit]


def save_report(user_id: str, message: str, context: dict, email: str | None = None) -> int:
    """Store a report and wake the sender. Returns its id."""
    now = time.time()
    with _lock:
        db = _db()
        with db:
            cursor = db.execute(
                "INSERT INTO reports (created_at, user_id, email, message, context, next_try_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (now, user_id, email, message, json.dumps(context, sort_keys=True), now),
            )
    _wake.set()
    return int(cursor.lastrowid)


def delete_user_reports(user_id: str) -> None:
    with _lock:
        db = _db()
        with db:
            db.execute("DELETE FROM reports WHERE user_id = ?", (user_id,))


def user_reports(user_id: str) -> list[dict]:
    """The user's reports, oldest first (for the data export)."""
    with _lock:
        rows = _db().execute(
            "SELECT created_at, message, context FROM reports WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    return [
        {"sent_at": formatdate(created, usegmt=True), "message": message, "context": json.loads(context)}
        for created, message, context in rows
    ]


def _header(value: str, limit: int = 120) -> str:
    return _HEADER_UNSAFE.sub(" ", value or "").strip()[:limit]


CONTEXT_LABELS = (
    ("source", "App"),
    ("app_version", "Version"),
    ("page", "Page"),
    ("user_agent", "Browser"),
    ("last_error", "Last error"),
)


def build_email(report_id: int, created_at: float, user_id: str, email: str | None,
                message: str, context: dict) -> EmailMessage:
    first_line = message.strip().splitlines()[0] if message.strip() else "(no message)"
    msg = EmailMessage()
    msg["Subject"] = _header(f"[MemoryLane report #{report_id}] {first_line}", 140)
    msg["From"] = REPORTS_FROM
    msg["To"] = REPORTS_TO
    if email:
        msg["Reply-To"] = _header(email, 254)
    msg["Date"] = formatdate(created_at, usegmt=True)
    msg["Message-ID"] = make_msgid(domain="memorylane.report")
    details = "\n".join(
        f"{label}: {context[key]}" for key, label in CONTEXT_LABELS if context.get(key)
    )
    msg.set_content(
        f"{message}\n\n"
        f"---\n"
        f"Report #{report_id}, {formatdate(created_at, usegmt=True)}\n"
        f"From: {email or '(email unknown)'}\n"
        f"Library id: {user_id}\n"
        f"{details}\n"
    )
    return msg


def send_email(msg: EmailMessage) -> None:
    """Send over SMTP with STARTTLS (or implicit TLS on port 465)."""
    if SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
    try:
        if SMTP_PORT != 465:
            server.starttls()
        if SMTP_USER:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def retry_delay(attempts: int) -> float:
    return min(RETRY_BASE_SECONDS * 2 ** max(attempts - 1, 0), RETRY_MAX_SECONDS)


def send_due(now: float | None = None) -> int:
    """Email every report that is due. Returns how many were sent."""
    if not email_enabled():
        return 0
    now = time.time() if now is None else now
    with _lock:
        due = _db().execute(
            "SELECT id, created_at, user_id, email, message, context, attempts FROM reports"
            " WHERE sent_at IS NULL AND attempts < ? AND next_try_at <= ? ORDER BY id LIMIT 20",
            (MAX_ATTEMPTS, now),
        ).fetchall()
    sent = 0
    for report_id, created, user_id, email, message, context, attempts in due:
        try:
            send_email(build_email(report_id, created, user_id, email, message, json.loads(context)))
        except Exception as e:
            attempts += 1
            # Never log the message itself; the error type and SMTP reply are enough.
            error = f"{type(e).__name__}: {str(e)[:200]}"
            logger.warning(f"Report #{report_id} not sent (attempt {attempts}): {error}")
            with _lock:
                db = _db()
                with db:
                    db.execute(
                        "UPDATE reports SET attempts = ?, next_try_at = ?, last_error = ? WHERE id = ?",
                        (attempts, now + retry_delay(attempts), error, report_id),
                    )
            continue
        with _lock:
            db = _db()
            with db:
                db.execute(
                    "UPDATE reports SET sent_at = ?, attempts = ?, last_error = NULL WHERE id = ?",
                    (time.time(), attempts + 1, report_id),
                )
        sent += 1
        logger.info(f"Report #{report_id} emailed")
    return sent


def _run() -> None:
    while not _stop.is_set():
        try:
            send_due()
        except Exception as e:  # keep the sender alive whatever happens
            logger.error(f"Report sender error: {type(e).__name__}")
        _wake.wait(SWEEP_SECONDS)
        _wake.clear()


def start_sender() -> None:
    """Start the background sender (once). Reports left unsent by an earlier
    run go out on its first pass."""
    global _thread
    if not email_enabled():
        logger.info("Report emails are off (SMTP_HOST, REPORTS_FROM or REPORTS_TO not set); "
                    "reports are stored only")
        return
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_run, name="report-sender", daemon=True)
    _thread.start()


def stop_sender() -> None:
    global _thread
    _stop.set()
    _wake.set()
    if _thread is not None:
        _thread.join(timeout=5)
    _thread = None


def reset_for_tests() -> None:
    global _conn
    stop_sender()
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
    _wake.clear()
    _stop.clear()
