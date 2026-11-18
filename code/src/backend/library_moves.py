"""Move pages from one library id to another, after sign-ins are linked.

A sign-in that isn't linked yet (its email unverified, or saved before linking
existed) stores pages under its own id. When it later links to a library that
another sign-in already started, accounts.py queues a move (old id -> library),
and this module carries the pages across, so they aren't stranded.

A page's id is derived from its owner (sha256(user_id | URL)), and chunk
embeddings aren't stored in Solr, so a page can't just be relabelled: each one is
re-ingested under the new library from its stored text (keeping its title, save
time and description), then deleted from the old one. When both libraries hold
the same URL, the newer save wins. Moves are stored in accounts.db, so a restart
picks up where it left off; a page that can't be stored is logged and left.
"""
import logging
import threading

from backend import accounts
from backend.chunking import join_chunks
from backend.ingest import IngestError, ingest_page
from backend.solr_client import SolrClient, get_solr_client
from backend.url_utils import generate_page_id

logger = logging.getLogger(__name__)

HEAD_FIELDS = "page_id,url,title,timestamp,description"
SWEEP_SECONDS = 300  # also retried this often after a failure (Solr down, say)
MAX_PAGES = 1_000_000

_thread = None
_stop = threading.Event()


def move_library(old: str, new: str, solr: SolrClient) -> dict:
    """Move every page of `old` into `new`. Returns counts; raises if Solr fails."""
    totals = {"moved": 0, "kept_newer": 0, "failed": 0}
    for head in list(solr.scan_page_heads(old, HEAD_FIELDS, MAX_PAGES)):
        page_id, url = head.get("page_id"), head.get("url") or ""
        if not page_id or not url:
            continue
        existing = solr.get_page_head(generate_page_id(new, url), new)
        if existing and str(existing.get("timestamp") or "") >= str(head.get("timestamp") or ""):
            totals["kept_newer"] += 1  # the library already has a newer save of this URL
        else:
            chunks = solr.get_chunks_by_page_id(page_id, old)
            text = join_chunks([c.get("text") or ""
                                for c in sorted(chunks, key=lambda c: int(c.get("chunk_id") or 0))])
            try:
                ingest_page(
                    new, url, head.get("title") or url, text, solr=solr,
                    timestamp=head.get("timestamp"), fetch_youtube=False, force=True,
                    description=head.get("description") or "",
                )
                totals["moved"] += 1
            except IngestError as e:
                totals["failed"] += 1
                logger.warning(f"Couldn't move page {page_id}: {e.detail}")
                continue  # leave it where it is rather than lose it
        solr.delete_page(page_id, old)
    return totals


def run_pending(solr: SolrClient | None = None) -> int:
    """Do every queued move. Returns how many finished."""
    finished = 0
    for old, new in accounts.pending_moves():
        try:
            totals = move_library(old, new, solr or get_solr_client())
        except Exception as e:  # Solr unreachable: try again on the next sweep
            logger.warning(f"Library move postponed ({type(e).__name__}: {e})")
            continue
        accounts.finish_move(old)
        finished += 1
        logger.info(f"Library move finished: {totals}")
    return finished


def _run() -> None:
    while not _stop.is_set():
        try:
            run_pending()
        except Exception as e:
            logger.error(f"Library mover error: {e}")
        accounts.moves_waiting.wait(SWEEP_SECONDS)
        accounts.moves_waiting.clear()


def start_mover() -> None:
    global _thread
    if not accounts.enabled() or (_thread and _thread.is_alive()):
        return
    _stop.clear()
    _thread = threading.Thread(target=_run, name="library-mover", daemon=True)
    _thread.start()


def stop_mover() -> None:
    _stop.set()
    accounts.moves_waiting.set()
