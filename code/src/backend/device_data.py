"""What the server keeps for pages stored on people's own devices.

Local-first MemoryLane keeps saved pages in the extension (IndexedDB), never on
the server. The server holds only two things for it, neither of which reveals a
page:

- a device key per library: random bytes the extension uses to encrypt its local
  copy at rest. The extension fetches it after sign-in and forgets it on
  sign-out, so a signed-out browser profile can't read the pages. The server
  has the key but never the pages.
- an encrypted backup per library: an opaque blob the extension encrypted with
  a recovery key that only the user has. The server stores and returns it; it
  can't read it, and nobody can without the recovery key.
"""
import hashlib
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from backend.config import ACCOUNTS_DB

# Next to accounts.db, on the same Docker volume.
DEVICE_DB = os.getenv("DEVICE_DB", os.path.join(os.path.dirname(ACCOUNTS_DB) or ".", "device.db"))
BACKUP_DIR = os.getenv("BACKUP_DIR", os.path.join(os.path.dirname(ACCOUNTS_DB) or ".", "backups"))
MAX_BACKUP_BYTES = int(os.getenv("MAX_BACKUP_BYTES", str(200 * 1024 * 1024)))
DEVICE_KEY_BYTES = 32

_lock = threading.Lock()
_conn = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        Path(DEVICE_DB).parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DEVICE_DB, check_same_thread=False)
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS device_keys ("
            " library TEXT PRIMARY KEY, key BLOB NOT NULL, created_at REAL NOT NULL)"
        )
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS backups ("
            " library TEXT PRIMARY KEY, bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, updated_at REAL NOT NULL)"
        )
        _conn.commit()
    return _conn


def reset_for_tests(db_path: str, backup_dir: str) -> None:
    global _conn, DEVICE_DB, BACKUP_DIR
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
        DEVICE_DB, BACKUP_DIR = db_path, backup_dir


def device_key(library: str) -> bytes:
    """The library's device key, created on first use."""
    with _lock:
        db = _db()
        row = db.execute("SELECT key FROM device_keys WHERE library = ?", (library,)).fetchone()
        if row:
            return bytes(row[0])
        key = secrets.token_bytes(DEVICE_KEY_BYTES)
        db.execute("INSERT INTO device_keys (library, key, created_at) VALUES (?, ?, ?)", (library, key, time.time()))
        db.commit()
        return key


def _backup_path(library: str) -> Path:
    # Library ids are validated user ids ([A-Za-z0-9-]); hash anyway so a name never reaches the filesystem.
    return Path(BACKUP_DIR) / (hashlib.sha256(library.encode()).hexdigest() + ".bin")


def save_backup(library: str, blob: bytes) -> dict:
    """Store (replace) the library's encrypted backup. Raises ValueError if too large or empty."""
    if not blob:
        raise ValueError("The backup is empty")
    if len(blob) > MAX_BACKUP_BYTES:
        raise ValueError(f"The backup is larger than {MAX_BACKUP_BYTES // (1024 * 1024)} MB")
    path = _backup_path(library)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, path)
    info = {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest(), "updated_at": time.time()}
    with _lock:
        db = _db()
        db.execute(
            "INSERT OR REPLACE INTO backups (library, bytes, sha256, updated_at) VALUES (?, ?, ?, ?)",
            (library, info["bytes"], info["sha256"], info["updated_at"]),
        )
        db.commit()
    return info


def backup_info(library: str) -> dict | None:
    with _lock:
        row = _db().execute("SELECT bytes, sha256, updated_at FROM backups WHERE library = ?", (library,)).fetchone()
    if not row or not _backup_path(library).exists():
        return None
    return {"bytes": row[0], "sha256": row[1], "updated_at": row[2]}


def load_backup(library: str) -> bytes | None:
    path = _backup_path(library)
    return path.read_bytes() if backup_info(library) and path.exists() else None


def delete_backup(library: str) -> None:
    _backup_path(library).unlink(missing_ok=True)
    with _lock:
        db = _db()
        db.execute("DELETE FROM backups WHERE library = ?", (library,))
        db.commit()


def forget_library(library: str) -> None:
    """Delete the backup and the device key (the local copy then can't be read again)."""
    delete_backup(library)
    with _lock:
        db = _db()
        db.execute("DELETE FROM device_keys WHERE library = ?", (library,))
        db.commit()
