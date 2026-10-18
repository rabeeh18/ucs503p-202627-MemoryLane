"""Re-index every page from one Solr core into another through ingest_page.

    python -m scripts.reindex --source-core memorylane --target-core memorylane_v2 \
        --user-id <cognito-sub> [--delete-user legacy] [--dry-run]

Pages are rebuilt from their stored chunks (joined with blank lines), keeping
url, title and timestamp, and re-ingested under --user-id. Old pages have no
HTML, so cleaning falls back to their text. The source core is never modified.
"""
import argparse
import logging
import sys
from urllib.parse import urlparse

from backend.chunking import join_chunks
from backend.config import SOLR_URL
from backend.ingest import IngestError, ingest_page
from backend.solr_client import SolrClient, is_valid_user_id

logger = logging.getLogger("reindex")

# The old core uses webpage_id; a v2 source core uses page_id.
SOURCE_FIELDS = "id,webpage_id,page_id,url,title,timestamp,text,chunk_id"


def solr_base_from_url(solr_url: str) -> str:
    """http://host:8983/solr/<core> -> http://host:8983/solr"""
    parsed = urlparse(solr_url)
    path = parsed.path.rstrip("/")
    if "/solr" in path:
        path = path[: path.index("/solr") + len("/solr")]
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def read_pages(source: SolrClient) -> list[dict]:
    """Group every chunk in the source core into pages, chunks sorted by chunk_id."""
    pages: dict[str, dict] = {}
    for doc in source.scan_unscoped(SOURCE_FIELDS):
        key = doc.get("webpage_id") or doc.get("page_id") or doc.get("url")
        if not key:
            continue
        page = pages.setdefault(key, {
            "url": doc.get("url"),
            "title": doc.get("title"),
            "timestamp": doc.get("timestamp"),
            "chunks": [],
        })
        page["chunks"].append((int(doc.get("chunk_id") or 0), doc.get("text") or ""))
    for page in pages.values():
        page["chunks"].sort(key=lambda c: c[0])
        page["text"] = join_chunks([text for _, text in page["chunks"]])
    return list(pages.values())


def reindex(source: SolrClient, target: SolrClient, user_id: str,
            delete_user: str | None = None, dry_run: bool = False) -> dict:
    pages = read_pages(source)
    totals = {"pages": len(pages), "source_chunks": sum(len(p["chunks"]) for p in pages),
              "saved": 0, "unchanged": 0, "skipped": 0, "chunks": 0, "failures": 0}

    if dry_run:
        if delete_user:
            print(f"[dry-run] would delete user_id={delete_user} from {target.base_url}")
        return totals

    if delete_user:
        print(f"Deleting user_id={delete_user} from {target.base_url}")
        target.delete_user(delete_user)

    for i, page in enumerate(pages, start=1):
        try:
            result = ingest_page(
                user_id, page["url"], page["title"] or "", page["text"],
                solr=target, timestamp=page["timestamp"], fetch_youtube=False,
            )
            totals[result.status] += 1
            totals["chunks"] += result.chunks if result.status == "saved" else 0
        except IngestError as e:
            totals["failures"] += 1
            print(f"  FAILED {page['url']}: {e.detail}")
        except Exception as e:
            totals["failures"] += 1
            print(f"  FAILED {page['url']}: {e}")
        if i % 25 == 0:
            print(f"  {i}/{len(pages)} pages processed")
    return totals


def main(argv=None):
    parser = argparse.ArgumentParser(description="Re-index MemoryLane pages into a new core")
    parser.add_argument("--source-core", required=True)
    parser.add_argument("--target-core", required=True)
    parser.add_argument("--user-id", required=True, help="Owner of the re-indexed pages (Cognito sub)")
    parser.add_argument("--delete-user", help="Delete this user's chunks from the target core first")
    parser.add_argument("--solr-base", default=solr_base_from_url(SOLR_URL),
                        help="Solr base URL (default: derived from SOLR_URL)")
    parser.add_argument("--dry-run", action="store_true", help="Read and count only; write nothing")
    args = parser.parse_args(argv)

    if args.source_core == args.target_core:
        parser.error("--source-core and --target-core must differ")
    for value in (args.user_id, args.delete_user):
        if value is not None and not is_valid_user_id(value):
            parser.error(f"invalid user id: {value!r} (letters, digits and '-' only)")

    logging.basicConfig(level=logging.WARNING)
    base = args.solr_base.rstrip("/")
    source = SolrClient(f"{base}/{args.source_core}")
    target = SolrClient(f"{base}/{args.target_core}")
    if not source.ping():
        sys.exit(f"Source core not reachable: {source.base_url}")
    if not args.dry_run and not target.ping():
        sys.exit(f"Target core not reachable: {target.base_url} (run scripts/setup_solr.sh first)")

    totals = reindex(source, target, args.user_id, args.delete_user, args.dry_run)

    print("")
    print(f"Pages:          {totals['pages']}")
    print(f"Source chunks:  {totals['source_chunks']}")
    if not args.dry_run:
        print(f"Saved:          {totals['saved']}")
        print(f"Unchanged:      {totals['unchanged']}")
        print(f"Skipped:        {totals['skipped']}")
        print(f"Chunks written: {totals['chunks']}")
        print(f"Failures:       {totals['failures']}")
    print("The source core was not modified.")
    return 1 if totals["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
