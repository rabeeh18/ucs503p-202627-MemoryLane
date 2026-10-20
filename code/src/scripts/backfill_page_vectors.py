"""Give every saved page a page vector (`page_embedding` on chunk 0).

    python -m scripts.backfill_page_vectors [--user-id <sub>] [--dry-run]

Each page without a vector is re-ingested through the normal ingest path from
its stored text (forced, so every chunk is rewritten with its embedding).
Solr atomic updates are deliberately NOT used: `embedding` is stored=false, so
an atomic update would silently drop every chunk's vector.

Resumable: pages that already have a vector are skipped, so re-running after
an interruption continues where it stopped. The page's url, title, saved time
and description are kept.
"""
import argparse
import sys
import time

from backend.chunking import join_chunks
from backend.config import SOLR_URL
from backend.ingest import IngestError, ingest_page
from backend.solr_client import SolrClient, is_valid_user_id, user_filter

HEAD_FIELDS = "page_id,user_id,url,title,timestamp,description,page_embedding"


def pages_to_backfill(solr: SolrClient, user_id: str | None):
    """(done, todo) page heads: `done` already have a page vector."""
    filters = ["chunk_id:0"] + ([user_filter(user_id)] if user_id else [])
    done, todo = [], []
    for head in solr.scan_unscoped(HEAD_FIELDS, filters=filters):
        if not head.get("user_id") or not head.get("page_id"):
            continue
        (done if head.get("page_embedding") else todo).append(head)
    return done, todo


def backfill(solr: SolrClient, user_id: str | None = None, dry_run: bool = False,
             log=print) -> dict:
    done, todo = pages_to_backfill(solr, user_id)
    totals = {"pages": len(done) + len(todo), "already_done": len(done), "todo": len(todo),
              "backfilled": 0, "failures": 0}
    log(f"{totals['pages']} pages: {len(done)} already have a vector, {len(todo)} to backfill")
    if dry_run:
        return totals

    started = time.monotonic()
    for i, head in enumerate(todo, start=1):
        owner, page_id = head["user_id"], head["page_id"]
        try:
            chunks = solr.get_chunks_by_page_id(page_id, owner)
            text = join_chunks([c.get("text") or "" for c in sorted(chunks, key=lambda c: int(c.get("chunk_id") or 0))])
            ingest_page(
                owner, head.get("url") or "", head.get("title") or "", text,
                solr=solr, timestamp=head.get("timestamp"), fetch_youtube=False,
                force=True, description=head.get("description") or "",
            )
            totals["backfilled"] += 1
        except (IngestError, Exception) as e:  # keep going; the page is retried next run
            totals["failures"] += 1
            log(f"  FAILED {head.get('url')}: {getattr(e, 'detail', e)}")
        if i % 10 == 0 or i == len(todo):
            elapsed = time.monotonic() - started
            log(f"  [{i}/{len(todo)}] backfilled={totals['backfilled']} failures={totals['failures']} "
                f"({elapsed:.0f}s)")
    return totals


def main(argv=None):
    parser = argparse.ArgumentParser(description="Backfill page vectors for the library map")
    parser.add_argument("--user-id", help="Only this user's pages (Cognito sub); default: every user")
    parser.add_argument("--solr-url", default=SOLR_URL, help="Core URL (default: SOLR_URL)")
    parser.add_argument("--dry-run", action="store_true", help="Count pages only; write nothing")
    args = parser.parse_args(argv)

    if args.user_id is not None and not is_valid_user_id(args.user_id):
        parser.error(f"invalid user id: {args.user_id!r}")

    solr = SolrClient(args.solr_url)
    if not solr.ping():
        sys.exit(f"Solr core not reachable: {solr.base_url}")
    totals = backfill(solr, args.user_id, args.dry_run)
    print("")
    for key, value in totals.items():
        print(f"{key.replace('_', ' ').capitalize():14} {value}")
    return 1 if totals["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
