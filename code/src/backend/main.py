import base64
import logging
import re
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend import accounts, device_data, library_moves, reports
from backend import config as search_config
from backend.auth import check_config, current_user_id
from backend.config import CORS_ORIGINS, MAX_PAGES_PER_USER, MIN_VECTOR_SIMILARITY
from backend.models import (
    MemoryInput, SearchInput, MemoryResponse, PageInfo, MemoryStatusResponse,
    MemoriesResponse, SearchResponse, SearchResultItem, DebugSearchResultItem,
    HealthResponse, SummarizeInput, SummarizeResponse, RelatedPage, RelatedResponse,
    ReportInput, ReportResponse, ExistingPagesInput, ExistingPagesResponse,
    SearchSettingsResponse, MeResponse, TransferInput, PageContentResponse,
    SummarizeTextInput, BackupInfoResponse,
)
from backend.embeddings import is_model_loaded, get_model
from backend.ingest import IngestError, ingest_page, resolve_canonical_url
from backend.solr_client import get_solr_client
from backend.page_filter import auto_capture_refusal
from backend.retrieval import forget_user_sites, hybrid_search, knn_score_to_cosine
from backend.summarizer import summarize, detect_detail_level, is_gemini_available
from backend.url_utils import normalize_url, generate_page_id

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DropQueryStrings(logging.Filter):
    """Uvicorn's access log without query strings: they hold the URLs people
    save (/memory/status?url=...)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str) and "?" in args[2]:
            record.args = (*args[:2], args[2].split("?", 1)[0], *args[3:])
        return True


logging.getLogger("uvicorn.access").addFilter(DropQueryStrings())

# httpx logs every request it makes at INFO, with the full URL. Solr queries go
# out as GET URLs carrying the user id and, for searches, the words searched for,
# and Cognito/Gemini calls would show up too, so keep only its warnings and errors.
QUIET_LOGGERS = ("httpx", "httpcore")
for _name in QUIET_LOGGERS:
    logging.getLogger(_name).setLevel(logging.WARNING)

_PAGE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_config()
    logger.info("Loading embedding model...")
    try:
        get_model()
        logger.info("Embedding model loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load embedding model: {e}")
    reports.start_sender()
    library_moves.start_mover()
    yield
    library_moves.stop_mover()
    reports.stop_sender()


app = FastAPI(
    title="MemoryLane",
    description="Personal browsing-memory retrieval system",
    version="1.0.0",
    lifespan=lifespan,
)


def _rate_limit_key(request: Request) -> str:
    """Per user once current_user_id has run, else per client IP."""
    user_id = getattr(request.state, "user_id", None)
    return f"user:{user_id}" if user_id else f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_rate_limit_key)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def rate_limit_exceeded(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded ({exc.detail}). Try again in a moment."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _page_info(doc: dict, with_chunks: bool = True) -> PageInfo:
    return PageInfo(
        id=doc.get("page_id") or "",
        url=doc.get("url") or "",
        title=doc.get("title") or "",
        domain=doc.get("domain") or "",
        timestamp=str(doc.get("timestamp") or ""),
        chunks=int(doc.get("total_chunks") or 0) if with_chunks else None,
    )


def _owned_page_id(page_id: str, user_id: str) -> str:
    """404 unless page_id is one of the caller's pages (indistinguishable from missing)."""
    page_id = (page_id or "").strip()
    if not _PAGE_ID_RE.match(page_id) or get_solr_client().get_page_head(page_id, user_id) is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return page_id


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint (public)."""
    solr_ok = False
    try:
        solr_ok = get_solr_client().ping()
    except Exception:
        pass

    embedding_ok = is_model_loaded()
    gemini_ok = is_gemini_available()

    status = "ok" if solr_ok and embedding_ok else "degraded"

    return HealthResponse(
        status=status,
        solr=solr_ok,
        embedding_model=embedding_ok,
        gemini=gemini_ok
    )


@app.post("/memory", response_model=MemoryResponse)
@limiter.limit("60/minute")
def save_memory(request: Request, memory: MemoryInput, user_id: str = Depends(current_user_id)):
    """Save a webpage to the caller's memory."""
    if not memory.is_manual:
        # The extension checks automatic saves itself; check again here, so an
        # outdated or misbehaving extension can't store an inbox or a login page.
        for address in filter(None, (memory.url, memory.canonical_url)):
            reason = auto_capture_refusal(address, memory.html)
            if reason:
                logger.info("Automatic save refused by the page rules")
                return MemoryResponse(status="skipped", message=reason, page=None)
    try:
        result = ingest_page(
            user_id,
            memory.url,
            memory.title,
            memory.content,
            html=memory.html,
            canonical_url=memory.canonical_url,
            is_manual=memory.is_manual,
            youtube=memory.youtube.model_dump() if memory.youtube else None,
            max_pages=MAX_PAGES_PER_USER,
            keep_existing=not memory.is_manual,
        )
    except IngestError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"Failed to save memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to save page")

    if result.status == "saved":
        forget_user_sites(user_id)

    page = None
    if result.status != "skipped":
        page = PageInfo(
            id=result.page_id, url=result.url, title=result.title, domain=result.domain,
            timestamp=result.timestamp, chunks=result.chunks,
        )
    return MemoryResponse(status=result.status, message=result.message, page=page)


@app.get("/memory/status", response_model=MemoryStatusResponse)
@limiter.limit("120/minute")
def memory_status(
    request: Request,
    url: str = Query(max_length=2048),
    canonical_url: str | None = Query(default=None, max_length=2048),
    user_id: str = Depends(current_user_id),
):
    """Whether the caller has saved this URL (normalized the same way as ingest)."""
    if not url.strip():
        raise HTTPException(status_code=400, detail="url is required")
    normalized = normalize_url(resolve_canonical_url(url, canonical_url))
    head = get_solr_client().get_page_head(generate_page_id(user_id, normalized), user_id)
    if head is None:
        return MemoryStatusResponse(saved=False)
    return MemoryStatusResponse(saved=True, page=_page_info(head))


@app.post("/memory/existing", response_model=ExistingPagesResponse)
@limiter.limit("120/minute")
def existing_pages(request: Request, body: ExistingPagesInput, user_id: str = Depends(current_user_id)):
    """Which of these page ids are still in the caller's library (the extension
    drops pages deleted on the website from its "Auto-saved today" list)."""
    ids = list(dict.fromkeys(i.strip() for i in body.ids if _PAGE_ID_RE.match(i.strip())))
    found = get_solr_client().existing_page_ids(user_id, ids)
    return ExistingPagesResponse(ids=[i for i in ids if i in found])


@app.delete("/memory/{page_id}", status_code=204)
@limiter.limit("60/minute")
def delete_memory(request: Request, page_id: str, user_id: str = Depends(current_user_id)):
    """Delete one of the caller's pages."""
    page_id = _owned_page_id(page_id, user_id)
    get_solr_client().delete_page(page_id, user_id)
    forget_user_sites(user_id)
    return Response(status_code=204)


@app.get("/memory/{page_id}/related", response_model=RelatedResponse)
@limiter.limit("120/minute")
def related_pages(
    request: Request,
    page_id: str,
    k: int = Query(default=5, ge=1, le=20),
    user_id: str = Depends(current_user_id),
):
    """The caller's pages most similar to one of their pages (by page vector)."""
    page_id = _owned_page_id(page_id, user_id)
    solr = get_solr_client()
    vector = solr.get_page_vector(page_id, user_id)
    if vector is None:  # saved before page vectors existed and not backfilled yet
        return RelatedResponse(page_id=page_id, related=[])
    related = []
    for doc in solr.related_pages(vector, user_id, exclude_page_id=page_id, k=k):
        similarity = knn_score_to_cosine(doc.get("score", 0.0))
        if doc.get("page_id") == page_id or similarity < MIN_VECTOR_SIMILARITY:
            continue
        related.append(RelatedPage(
            id=doc.get("page_id") or "",
            title=doc.get("title") or doc.get("url") or "",
            url=doc.get("url") or "",
            domain=doc.get("domain") or "",
            saved_at=str(doc.get("timestamp") or ""),
            similarity=round(similarity, 4),
        ))
    return RelatedResponse(page_id=page_id, related=related)


@app.get("/memories", response_model=MemoriesResponse)
@limiter.limit("60/minute")
def list_memories(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    user_id: str = Depends(current_user_id),
):
    """The caller's saved pages, newest first."""
    total, docs = get_solr_client().list_pages(user_id, limit=limit, offset=offset)
    return MemoriesResponse(total=total, pages=[_page_info(d, with_chunks=False) for d in docs])


def _page_text(page_id: str, user_id: str) -> str | None:
    chunks = get_solr_client().get_chunks_by_page_id(page_id, user_id)
    if not chunks:
        return None
    return "\n\n".join(c.get("text") or "" for c in chunks)


def _summary_for_webpage(query: str, page_id: str, user_id: str) -> str | None:
    """Reuse the same Gemini path as POST /summarize, for one page."""
    if not is_gemini_available():
        return None
    full_text = _page_text(page_id, user_id)
    if not full_text or not full_text.strip():
        return None
    return summarize(query, full_text, detect_detail_level(query))


@app.post("/summarize", response_model=SummarizeResponse)
@limiter.limit("20/minute")
def summarize_memory(request: Request, body: SummarizeInput, user_id: str = Depends(current_user_id)):
    """On-demand summary for one of the caller's pages. Does not run search."""
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")
    if not body.id or not body.id.strip():
        raise HTTPException(status_code=400, detail="id is required")

    page_id = body.id.strip()
    full_text = _page_text(page_id, user_id) if _PAGE_ID_RE.match(page_id) else None
    if full_text is None:
        raise HTTPException(status_code=404, detail="Page not found")

    if not is_gemini_available():
        raise HTTPException(status_code=503, detail="Summarization is unavailable")

    summary = summarize(body.query.strip(), full_text, detect_detail_level(body.query))
    if not summary:
        raise HTTPException(status_code=502, detail="Summarization failed")

    return SummarizeResponse(id=page_id, summary=summary)


@app.post("/search", response_model=SearchResponse)
@limiter.limit("60/minute")
def search_memory(request: Request, search: SearchInput, user_id: str = Depends(current_user_id)):
    """Search the caller's saved pages."""
    logger.info("Search started")

    if not search.query or not search.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")

    try:
        timings = {}
        results = hybrid_search(search.query, user_id, top_k=search.num_results, timings=timings)

        response_results = []
        for result in results:
            summary = None
            if search.summarize:
                summary = _summary_for_webpage(search.query, result["page_id"], user_id)

            fields = dict(
                rank=result["rank"],
                id=result["page_id"],
                title=result.get("title", ""),
                url=result.get("url", ""),
                domain=result.get("domain", ""),
                timestamp=str(result.get("timestamp") or ""),
                snippet=result.get("snippet"),
                summary=summary,
            )
            if search.debug:
                item = DebugSearchResultItem(
                    **fields,
                    bm25_rank=result.get("bm25_rank"),
                    knn_rank=result.get("knn_rank"),
                    fused_score=result.get("fused_score", 0.0),
                    rerank_score=result.get("rerank_score"),
                    vector_similarity=result.get("vector_similarity"),
                )
            else:
                item = SearchResultItem(**fields)
            response_results.append(item)

        logger.info(f"Returning {len(response_results)} results")
        return SearchResponse(
            query=search.query,
            results=response_results,
            timings=timings if search.debug else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail="Search failed")


@app.delete("/me/data", status_code=204)
@limiter.limit("5/minute")
def delete_my_data(request: Request, user_id: str = Depends(current_user_id)):
    """Delete every chunk the caller owns, including pages still being moved into
    their library from a sign-in that was linked recently."""
    solr = get_solr_client()
    solr.delete_user(user_id)
    for old in accounts.moves_into(user_id):
        solr.delete_user(old)
    forget_user_sites(user_id)
    reports.delete_user_reports(user_id)
    device_data.forget_library(user_id)
    accounts.forget_library(user_id)
    return Response(status_code=204)


_PAGE_PATH = re.compile(r"^/[A-Za-z0-9/_\-.]*$")


@app.post("/reports", response_model=ReportResponse, status_code=202)
@limiter.limit("5/hour")
def report_problem(request: Request, body: ReportInput, user_id: str = Depends(current_user_id)):
    """Store a problem report and queue it for email. 202 once it is on disk."""
    message = reports.clean_text(body.message, 4000)
    if not message:
        raise HTTPException(status_code=400, detail="Describe the problem first")
    ctx = body.context
    page = reports.clean_text(ctx.page, 200).split("?", 1)[0].split("#", 1)[0]
    context = {
        "source": body.source,
        "app_version": reports.clean_text(ctx.app_version, 40),
        "page": page if _PAGE_PATH.match(page) else "",
        "user_agent": reports.clean_text(ctx.user_agent, 400),
        "last_error": reports.clean_text(ctx.last_error, 500),
    }
    try:
        email = accounts.email_for(user_id)
    except Exception:
        email = None
    try:
        report_id = reports.save_report(user_id, message, context, email=email)
    except Exception as e:
        logger.error(f"Failed to store report: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Couldn't send your report. Try again.")
    return ReportResponse(status="received", id=report_id)


# ---- pages kept on the user's device (local-first) -------------------------------
#
# The extension can keep pages in the browser instead of on this server. These
# endpoints never receive a stored page except when the user moves one here
# (transfer) or asks for one page's summary; see backend/device_data.py.

_SEARCH_SETTING_NAMES = list(SearchSettingsResponse.model_fields)


@app.get("/search-settings", response_model=SearchSettingsResponse)
def search_settings():
    """The settings search runs with (public), so local search matches this server's."""
    return SearchSettingsResponse(**{name: getattr(search_config, name) for name in _SEARCH_SETTING_NAMES})


@app.get("/me", response_model=MeResponse)
@limiter.limit("60/minute")
def me(request: Request, user_id: str = Depends(current_user_id)):
    """The caller's library id (page ids are derived from it) and device key."""
    key = base64.urlsafe_b64encode(device_data.device_key(user_id)).decode().rstrip("=")
    return MeResponse(library_id=user_id, device_key=key)


@app.post("/memory/transfer", response_model=MemoryResponse)
@limiter.limit("120/minute")
def transfer_memory(request: Request, body: TransferInput, user_id: str = Depends(current_user_id)):
    """Store a page the extension kept locally, exactly as it was first saved
    (same cleaned text, title, description and save time), so it chunks, embeds
    and ranks the same here."""
    try:
        if sum(len(c) for c in body.chunks) > 2_000_000:
            raise IngestError(413, "This page is too long")
        result = ingest_page(
            user_id, body.url, body.title, "",
            is_manual=True, fetch_youtube=False, prepared_chunks=body.chunks,
            content_hash=body.content_hash, timestamp=body.timestamp,
            description=body.description, max_pages=MAX_PAGES_PER_USER,
        )
    except IngestError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"Failed to transfer a page: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Failed to save page")
    if result.status == "saved":
        forget_user_sites(user_id)
    page = PageInfo(id=result.page_id, url=result.url, title=result.title, domain=result.domain,
                    timestamp=result.timestamp, chunks=result.chunks)
    return MemoryResponse(status=result.status, message=result.message, page=page)


@app.get("/memory/{page_id}/content", response_model=PageContentResponse)
@limiter.limit("120/minute")
def page_content(request: Request, page_id: str, user_id: str = Depends(current_user_id)):
    """One of the caller's pages with its chunks, for moving it to the extension's local store."""
    page_id = _owned_page_id(page_id, user_id)
    chunks = get_solr_client().get_chunks_by_page_id(page_id, user_id)
    head = chunks[0]
    return PageContentResponse(
        id=page_id, url=head.get("url") or "", title=head.get("title") or "",
        description=head.get("description") or "", timestamp=str(head.get("timestamp") or ""),
        content_hash=head.get("content_hash") or "", chunks=[c.get("text") or "" for c in chunks],
    )


@app.post("/summarize/text", response_model=SummarizeResponse)
@limiter.limit("20/minute")
def summarize_text(request: Request, body: SummarizeTextInput, user_id: str = Depends(current_user_id)):
    """A summary of a page kept on the caller's device. Its text is used for this
    request only: not stored, not logged."""
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")
    if not is_gemini_available():
        raise HTTPException(status_code=503, detail="Summarization is unavailable")
    summary = summarize(body.query.strip(), body.text, detect_detail_level(body.query))
    if not summary:
        raise HTTPException(status_code=502, detail="Summarization failed")
    return SummarizeResponse(id="", summary=summary)


@app.get("/backup/info", response_model=BackupInfoResponse)
@limiter.limit("60/minute")
def backup_info(request: Request, user_id: str = Depends(current_user_id)):
    info = device_data.backup_info(user_id)
    if info is None:
        raise HTTPException(status_code=404, detail="No backup")
    return BackupInfoResponse(**info)


@app.put("/backup", response_model=BackupInfoResponse)
@limiter.limit("10/hour")
async def put_backup(request: Request, user_id: str = Depends(current_user_id)):
    """Store the caller's encrypted backup (an opaque blob only their recovery key opens)."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > device_data.MAX_BACKUP_BYTES:
        raise HTTPException(status_code=413, detail="The backup is too large")
    blob = bytearray()
    async for part in request.stream():
        blob.extend(part)
        if len(blob) > device_data.MAX_BACKUP_BYTES:
            raise HTTPException(status_code=413, detail="The backup is too large")
    try:
        info = device_data.save_backup(user_id, bytes(blob))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return BackupInfoResponse(**info)


@app.get("/backup")
@limiter.limit("10/hour")
def get_backup(request: Request, user_id: str = Depends(current_user_id)):
    blob = device_data.load_backup(user_id)
    if blob is None:
        raise HTTPException(status_code=404, detail="No backup")
    return Response(content=blob, media_type="application/octet-stream")


@app.delete("/backup", status_code=204)
@limiter.limit("10/minute")
def delete_backup(request: Request, user_id: str = Depends(current_user_id)):
    device_data.delete_backup(user_id)
    return Response(status_code=204)
