import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.config import SOLR_URL
from backend.models import (
    MemoryInput, SearchInput, MemoryResponse, MemoryMetadata,
    SearchResponse, SearchResultItem, DebugSearchResultItem, HealthResponse,
    SummarizeInput, SummarizeResponse,
)
from backend.url_utils import normalize_url, generate_webpage_id
from backend.chunking import chunk_text
from backend.embeddings import get_embedding, get_embeddings, is_model_loaded, get_model
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

# CORS for browser extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
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
async def save_memory(memory: MemoryInput):
    """Save a webpage to memory."""
    logger.info(f"Memory received: {memory.url}")
    
    # Validate
    if not memory.url or not memory.url.strip():
        raise HTTPException(status_code=400, detail="URL is required")
    if not memory.title or not memory.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    if not memory.content or not memory.content.strip():
        raise HTTPException(status_code=400, detail="Content is required")
    
    try:
        # Normalize URL
        normalized_url = normalize_url(memory.url)
        webpage_id = generate_webpage_id(normalized_url)
        logger.info(f"Normalized URL: {normalized_url}, webpage_id: {webpage_id}")
        
        # Parse domain
        from urllib.parse import urlparse
        domain = urlparse(normalized_url).netloc
        
        # Chunk content
        logger.info("Chunking webpage content")
        chunks = chunk_text(memory.content)
        logger.info(f"Generated {len(chunks)} chunks")
        
        # Generate embeddings
        logger.info("Generating embeddings")
        embeddings = get_embeddings(chunks)
        logger.info(f"Generated {len(embeddings)} embeddings")
        
        # Delete old chunks
        solr = get_solr_client()
        logger.info(f"Deleting old chunks for webpage_id: {webpage_id}")
        solr.delete_by_query(f'webpage_id:"{webpage_id}"')
        
        # Build Solr documents
        timestamp = datetime.now(timezone.utc).isoformat()
        docs = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            doc = {
                "id": f"{webpage_id}::chunk::{i}",
                "webpage_id": webpage_id,
                "url": normalized_url,
                "title": memory.title,
                "domain": domain,
                "text": chunk,
                "chunk_id": i,
                "total_chunks": len(chunks),
                "timestamp": timestamp,
                "embedding": embedding,
            }
            docs.append(doc)
        
        # Index
        logger.info(f"Indexing {len(docs)} documents")
        solr.add_documents(docs)
        logger.info("Webpage indexed successfully")
        
        return MemoryResponse(
            success=True,
            message="Memory stored successfully",
            metadata=MemoryMetadata(
                url=normalized_url,
                title=memory.title,
                id=webpage_id,
                chunks=len(chunks),
                timestamp=timestamp
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _summary_for_webpage(query: str, webpage_id: str) -> str | None:
    """Reuse the same Gemini path as POST /search?summarize=true, for one page."""
    if not is_gemini_available():
        return None
    chunks = get_solr_client().get_chunks_by_webpage_id(webpage_id)
    if not chunks:
        return None
    full_text = "\n\n".join(c.get("text") or "" for c in chunks)
    if not full_text.strip():
        return None
    return summarize(query, full_text, detect_detail_level(query))


@app.post("/summarize", response_model=SummarizeResponse)
async def summarize_memory(body: SummarizeInput):
    """On-demand summary for a single indexed webpage. Does not run search."""
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")
    if not body.id or not body.id.strip():
        raise HTTPException(status_code=400, detail="id is required")

    webpage_id = body.id.strip()
    chunks = get_solr_client().get_chunks_by_webpage_id(webpage_id)
    if not chunks:
        raise HTTPException(status_code=404, detail="Webpage not found")

    if not is_gemini_available():
        raise HTTPException(status_code=503, detail="Summarization is unavailable")

    full_text = "\n\n".join(c.get("text") or "" for c in chunks)
    summary = summarize(body.query.strip(), full_text, detect_detail_level(body.query))
    if not summary:
        raise HTTPException(status_code=502, detail="Summarization failed")

    return SummarizeResponse(id=webpage_id, summary=summary)


@app.post("/search", response_model=SearchResponse)
async def search_memory(search: SearchInput):
    """Search saved memories."""
    logger.info(f"Search started: {search.query}")
    
    if not search.query or not search.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")
    
    try:
        # Hybrid search
        results = hybrid_search(search.query, top_k=search.num_results)
        
        # Build response
        response_results = []
        for result in results:
            summary = None
            if search.summarize:
                summary = _summary_for_webpage(search.query, result["webpage_id"])
            
            if search.debug:
                item = DebugSearchResultItem(
                    rank=result["rank"],
                    id=result["webpage_id"],
                    title=result.get("title", ""),
                    url=result.get("url", ""),
                    domain=result.get("domain", ""),
                    timestamp=result.get("timestamp", ""),
                    summary=summary,
                    bm25_score=result.get("bm25_score", 0.0),
                    vector_score=result.get("vector_score", 0.0),
                    fused_score=result.get("fused_score", 0.0)
                )
            else:
                item = SearchResultItem(
                    rank=result["rank"],
                    id=result["webpage_id"],
                    title=result.get("title", ""),
                    url=result.get("url", ""),
                    domain=result.get("domain", ""),
                    timestamp=result.get("timestamp", ""),
                    summary=summary
                )
            response_results.append(item)
        
        logger.info(f"Returning {len(response_results)} results")
        return SearchResponse(query=search.query, results=response_results)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
