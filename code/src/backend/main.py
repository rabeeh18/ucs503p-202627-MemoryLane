import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.config import CORS_ORIGINS, LEGACY_USER_ID
from backend.models import (
    MemoryInput, SearchInput, MemoryResponse, MemoryMetadata,
    SearchResponse, SearchResultItem, DebugSearchResultItem, HealthResponse,
    SummarizeInput, SummarizeResponse,
)
from backend.embeddings import is_model_loaded, get_model
from backend.ingest import IngestError, ingest_page
from backend.solr_client import get_solr_client
from backend.retrieval import hybrid_search
from backend.summarizer import summarize, detect_detail_level, is_gemini_available

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
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

# Keyed by client IP until authentication exists.
limiter = Limiter(key_func=get_remote_address)
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


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint."""
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
def save_memory(request: Request, memory: MemoryInput):
    """Save a webpage to memory."""
    logger.info(f"Memory received: {memory.url}")
    try:
        result = ingest_page(
            LEGACY_USER_ID,
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
        raise HTTPException(status_code=500, detail=str(e))

    return MemoryResponse(
        success=True,
        status=result.status,
        message=result.message,
        metadata=MemoryMetadata(
            url=result.url,
            title=result.title,
            id=result.page_id,
            chunks=result.chunks,
            timestamp=result.timestamp,
        ),
    )


def _summary_for_webpage(query: str, page_id: str) -> str | None:
    """Reuse the same Gemini path as POST /search?summarize=true, for one page."""
    if not is_gemini_available():
        return None
    chunks = get_solr_client().get_chunks_by_page_id(page_id)
    if not chunks:
        return None
    full_text = "\n\n".join(c.get("text") or "" for c in chunks)
    if not full_text.strip():
        return None
    return summarize(query, full_text, detect_detail_level(query))


@app.post("/summarize", response_model=SummarizeResponse)
@limiter.limit("20/minute")
def summarize_memory(request: Request, body: SummarizeInput):
    """On-demand summary for a single indexed webpage. Does not run search."""
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")
    if not body.id or not body.id.strip():
        raise HTTPException(status_code=400, detail="id is required")

    page_id = body.id.strip()
    chunks = get_solr_client().get_chunks_by_page_id(page_id)
    if not chunks:
        raise HTTPException(status_code=404, detail="Webpage not found")

    if not is_gemini_available():
        raise HTTPException(status_code=503, detail="Summarization is unavailable")

    full_text = "\n\n".join(c.get("text") or "" for c in chunks)
    summary = summarize(body.query.strip(), full_text, detect_detail_level(body.query))
    if not summary:
        raise HTTPException(status_code=502, detail="Summarization failed")

    return SummarizeResponse(id=page_id, summary=summary)


@app.post("/search", response_model=SearchResponse)
@limiter.limit("60/minute")
def search_memory(request: Request, search: SearchInput):
    """Search saved memories."""
    logger.info(f"Search started: {search.query}")
    
    if not search.query or not search.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")
    
    try:
        # Hybrid search
        timings = {}
        results = hybrid_search(search.query, top_k=search.num_results, timings=timings)
        
        # Build response
        response_results = []
        for result in results:
            summary = None
            if search.summarize:
                summary = _summary_for_webpage(search.query, result["page_id"])
            
            fields = dict(
                rank=result["rank"],
                id=result["page_id"],
                title=result.get("title", ""),
                url=result.get("url", ""),
                domain=result.get("domain", ""),
                timestamp=result.get("timestamp", ""),
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
        raise HTTPException(status_code=500, detail=str(e))
