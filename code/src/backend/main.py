import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.auth import check_config, current_user_id
from backend.config import CORS_ORIGINS
from backend.models import (
    MemoryInput, SearchInput, MemoryResponse, PageInfo, MemoryStatusResponse,
    MemoriesResponse, SearchResponse, SearchResultItem, DebugSearchResultItem,
    HealthResponse, SummarizeInput, SummarizeResponse,
)
from backend.chunking import join_chunks
from backend.embeddings import is_model_loaded, get_model
from backend.ingest import IngestError, ingest_page, resolve_canonical_url
from backend.solr_client import get_solr_client
from backend.retrieval import hybrid_search
from backend.summarizer import summarize, detect_detail_level, is_gemini_available
from backend.url_utils import normalize_url, generate_page_id

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
    yield


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
    logger.info(f"Memory received: {memory.url}")
    try:
        result = ingest_page(
            user_id,
            memory.url,
            memory.title,
            memory.content,
            html=memory.html,
            canonical_url=memory.canonical_url,
            is_manual=memory.is_manual,
        )
    except IngestError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"Failed to save memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to save page")

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


@app.delete("/memory/{page_id}", status_code=204)
@limiter.limit("60/minute")
def delete_memory(request: Request, page_id: str, user_id: str = Depends(current_user_id)):
    """Delete one of the caller's pages."""
    page_id = _owned_page_id(page_id, user_id)
    get_solr_client().delete_page(page_id, user_id)
    return Response(status_code=204)


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


@app.get("/me/export")
@limiter.limit("5/minute")
def export_my_data(request: Request, user_id: str = Depends(current_user_id)):
    """Download every page the caller has saved, with its full text."""
    pages: dict[str, dict] = {}
    for doc in get_solr_client().scan("page_id,url,title,timestamp,text,chunk_id", user_id):
        page = pages.setdefault(doc.get("page_id"), {
            "url": doc.get("url"), "title": doc.get("title"),
            "timestamp": str(doc.get("timestamp") or ""), "chunks": [],
        })
        page["chunks"].append((int(doc.get("chunk_id") or 0), doc.get("text") or ""))

    exported = []
    for page in sorted(pages.values(), key=lambda p: p["timestamp"], reverse=True):
        chunks = [text for _, text in sorted(page.pop("chunks"))]
        exported.append({**page, "text": join_chunks(chunks)})

    return JSONResponse(
        content={
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "pages": exported,
        },
        headers={"Content-Disposition": 'attachment; filename="memorylane-export.json"'},
    )


@app.delete("/me/data", status_code=204)
@limiter.limit("5/minute")
def delete_my_data(request: Request, user_id: str = Depends(current_user_id)):
    """Delete every chunk the caller owns."""
    get_solr_client().delete_user(user_id)
    return Response(status_code=204)
