import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from backend.chunking import chunk_text
from backend.cleaning import clean_content, extract_description, word_count
from backend.config import EMBEDDING_MODEL, MIN_CONTENT_WORDS
from backend.embeddings import embed_passages
from backend.solr_client import SolrClient, get_solr_client, is_valid_user_id
from backend.url_utils import normalize_url, generate_page_id
from backend.youtube_utils import is_youtube_url, process_youtube_video

logger = logging.getLogger(__name__)

NOT_ENOUGH_TEXT = "Not enough readable text on this page"


class IngestError(Exception):
    """A page that can't be ingested; status_code maps onto the HTTP response."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class IngestResult:
    status: str  # "saved" | "unchanged" | "skipped"
    message: str
    page_id: str
    url: str
    title: str
    domain: str
    timestamp: str
    chunks: int


def to_solr_date(value: str | datetime | None = None) -> str:
    """UTC ISO-8601 with a Z suffix, as Solr's pdate requires. Unparseable or
    missing values become the current time."""
    if isinstance(value, str) and value.strip():
        try:
            value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            value = None
    if not isinstance(value, datetime):
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def resolve_canonical_url(url: str, canonical_url: str | None) -> str:
    """Use the page's canonical URL (resolved against url) when it is a valid http(s) URL."""
    if canonical_url and canonical_url.strip():
        try:
            resolved = urljoin(url, canonical_url.strip())
            parsed = urlparse(resolved)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                return resolved
        except Exception:
            pass
    return url


def ingest_page(user_id: str, url: str, title: str, text: str, html: str | None = None,
                canonical_url: str | None = None, is_manual: bool = False, *,
                solr: SolrClient | None = None, timestamp: str | None = None,
                fetch_youtube: bool = True) -> IngestResult:
    """Clean, chunk, embed and store one page for one user.

    Used by the API, the re-index script and the evaluation scripts. `solr`
    targets a specific core (default: SOLR_URL), `timestamp` keeps an original
    save time, and `fetch_youtube=False` uses `text` as-is for YouTube URLs.
    Raises IngestError for pages that can't be stored.
    """
    if not is_valid_user_id(user_id):
        raise ValueError("ingest_page needs a valid user_id")
    if not url or not url.strip():
        raise IngestError(400, "URL is required")
    solr = solr or get_solr_client()
    domain = urlparse(url).netloc

    youtube_content = None
    if fetch_youtube and is_youtube_url(url):
        youtube_content, yt_title, skip = process_youtube_video(url, is_manual)
        if skip:
            return IngestResult("skipped", skip, "", url, title or domain, domain, "", 0)
        title = yt_title

    if not title or not title.strip() or title.strip().lower() in ("untitled", "untitled document"):
        title = domain
    title = title.strip()

    # 1-2. Canonical + normalized URL, per-user page id
    normalized_url = normalize_url(resolve_canonical_url(url, canonical_url))
    page_id = generate_page_id(user_id, normalized_url)
    domain = urlparse(normalized_url).netloc
    logger.info(f"Normalized URL: {normalized_url}, page_id: {page_id}")

    # 3. YouTube transcript, otherwise cleaned page text
    if youtube_content is not None:
        cleaned = youtube_content
    else:
        cleaned = clean_content(html, text or "")
        if word_count(cleaned) < MIN_CONTENT_WORDS:
            raise IngestError(422, NOT_ENOUGH_TEXT)

    # 4. Unchanged content (and same embedding model) needs no work
    content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    existing = solr.get_page_head(page_id, user_id)
    if existing and existing.get("content_hash") == content_hash \
            and existing.get("embedding_model") == EMBEDDING_MODEL \
            and "description" in existing:
        # (Pages stored before `description` existed are re-ingested once to gain it.)
        logger.info(f"Unchanged page: {normalized_url}")
        return IngestResult(
            "unchanged", "Memory already stored", page_id,
            existing.get("url") or normalized_url,
            existing.get("title") or title,
            existing.get("domain") or domain,
            str(existing.get("timestamp") or ""),
            int(existing.get("total_chunks") or 0),
        )

    # 5. Chunk, embed title + chunk, build docs
    chunks = chunk_text(cleaned)
    if not chunks:
        raise IngestError(422, NOT_ENOUGH_TEXT)
    embeddings = embed_passages([f"{title}\n\n{chunk}" for chunk in chunks])
    saved_at = to_solr_date(timestamp)
    description = extract_description(None if youtube_content is not None else html, cleaned)
    docs = [
        {
            "id": f"{page_id}::{i}",
            "user_id": user_id,
            "page_id": page_id,
            "url": normalized_url,
            "title": title,
            "domain": domain,
            "text": chunk,
            "description": description,
            "chunk_id": i,
            "total_chunks": len(chunks),
            "timestamp": saved_at,
            "content_hash": content_hash,
            "embedding_model": EMBEDDING_MODEL,
            "embedding": embedding,
        }
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]

    # 6. Overwrite in place, then drop stale chunks
    solr.upsert_page_chunks(page_id, docs, user_id)
    logger.info(f"Indexed {len(docs)} chunks for {normalized_url}")
    return IngestResult(
        "saved", "Memory stored successfully", page_id, normalized_url,
        title, domain, saved_at, len(chunks),
    )
