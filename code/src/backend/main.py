# MemoryLane backend — receives a webpage from the userscript, embeds it,
# stores it in ChromaDB. That's it. Summarization happens later, in
# query.py, via Gemini — not here.

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
import os
import re
from datetime import datetime
from typing import List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # fine if GEMINI_API_KEY is set some other way

from hybrid_search import BM25Index, hybrid_search, DEFAULT_CANDIDATE_POOL, DEFAULT_RRF_K

app = FastAPI(title="MemoryLane Backend")

# wide open CORS since this only ever runs on localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("[MemoryLane] Loading Sentence Transformer model 'all-MiniLM-L6-v2'...")
try:
    embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    print("[MemoryLane] ✓ Model loaded successfully")
except Exception as e:
    print(f"[MemoryLane] ✗ Failed to load model: {e}")
    raise

print("[MemoryLane] Initializing ChromaDB...")
try:
    db_path = "./chroma_db"
    os.makedirs(db_path, exist_ok=True)

    chroma_client = chromadb.PersistentClient(path=db_path)
    collection = chroma_client.get_or_create_collection(
        name="memorylane",
        metadata={"hnsw:space": "cosine"}
    )
    print(f"[MemoryLane] ✓ ChromaDB initialized at {db_path}")
    print(f"[MemoryLane] ✓ Collection 'memorylane' ready")
except Exception as e:
    print(f"[MemoryLane] ✗ Failed to initialize ChromaDB: {e}")
    raise

print("[MemoryLane] Building BM25 index from ChromaDB...")
try:
    bm25_index = BM25Index()
    bm25_doc_count = bm25_index.build_from_chromadb(collection)
    print(f"[MemoryLane] ✓ BM25 index built ({bm25_doc_count} document(s))")
except Exception as e:
    # BM25 is a retrieval enhancement, not a hard requirement — if it fails
    # to build, search still works semantic-only rather than the whole
    # server refusing to start.
    print(f"[MemoryLane] ✗ Failed to build BM25 index (search will fall back to semantic-only): {e}")
    bm25_index = BM25Index()


class WebpageData(BaseModel):
    # matches what the Tampermonkey script sends
    url: str
    title: str
    content: str


class SearchQuery(BaseModel):
    query: str
    num_results: int = 5
    summarize: bool = True
    mode: str = "hybrid"  # "hybrid" | "semantic" | "bm25"
    debug: bool = False   # include bm25_score/semantic_score/hybrid_score per result


# ── Search + summarization (ported from query.py) ──────────────────────────
# Reuses the embedding_model and collection already loaded above instead of
# loading a second copy of MiniLM — query.py stays as a standalone CLI for
# terminal use, this is the same logic exposed as an HTTP endpoint for the
# extension.

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

_gemini_client = None
_gemini_init_error = None


def get_gemini_client():
    global _gemini_client, _gemini_init_error
    if _gemini_client is not None or _gemini_init_error is not None:
        return _gemini_client
    if not GEMINI_API_KEY:
        _gemini_init_error = "GEMINI_API_KEY is not set"
        print(f"[MemoryLane] ✗ Gemini not configured: {_gemini_init_error}")
        return None
    try:
        from google import genai
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        print(f"[MemoryLane] ✓ Gemini API key loaded (model: {GEMINI_MODEL})")
    except Exception as e:
        _gemini_init_error = str(e)
        print(f"[MemoryLane] ✗ Failed to initialize Gemini client: {e}")
        _gemini_client = None
    return _gemini_client


SHORT_PATTERNS = [
    r"\bbriefly\b", r"\bquickly\b", r"\bin short\b", r"\bjust remind\b",
    r"\bshort summary\b", r"\bshortly\b", r"\btl;?dr\b", r"\bin brief\b",
]
LONG_PATTERNS = [
    r"\bdetailed\b", r"\bin depth\b", r"\bin-depth\b", r"\bexplain fully\b",
    r"\bdetailed summary\b", r"\bfull summary\b", r"\bthorough\b",
    r"\bcomprehensive\b", r"\beverything about\b", r"\bexplain in detail\b",
]
DETAIL_GUIDANCE = {
    "SHORT": "Keep it very brief: 1-2 sentences, just enough to jog the user's memory.",
    "MEDIUM": "Write a short paragraph: about 3-5 sentences covering the main points.",
    "LONG": "Write a detailed summary: 2-3 short paragraphs covering the page thoroughly.",
}
MAX_OUTPUT_TOKENS = {"SHORT": 120, "MEDIUM": 300, "LONG": 600}
MAX_CONTENT_WORDS = 4000


def detect_length_category(query_text: str) -> str:
    text = query_text.lower()
    for pattern in LONG_PATTERNS:
        if re.search(pattern, text):
            return "LONG"
    for pattern in SHORT_PATTERNS:
        if re.search(pattern, text):
            return "SHORT"
    return "MEDIUM"


def _build_prompt(webpage_content: str, user_query: str, detail_level: str) -> str:
    guidance = DETAIL_GUIDANCE.get(detail_level, DETAIL_GUIDANCE["MEDIUM"])
    return f"""You are helping a user recover a webpage from their browsing memory.

WEBPAGE CONTENT (the only source of truth — do not use any outside knowledge):
\"\"\"
{webpage_content}
\"\"\"

USER'S MEMORY/QUERY:
"{user_query}"

DETAIL LEVEL: {detail_level}
{guidance}

TASK:
Summarize the webpage content above for a user who is trying to remember
this webpage. Use the user's query only to decide which aspects of the
webpage to emphasize — do not explain why the page matches the query, and
do not mention the query, retrieval, or similarity scores at all.

Rules:
- Summarize the actual webpage. Do not invent, guess, or add information
  that is not present in the webpage content.
- Do not say things like "this page matches because..." or "this is
  relevant to your query because...".
- Do not mention that this is a summary, a search result, or a retrieval.
- Respect the requested detail level.
- Return ONLY the summary text itself — no preamble, no headers, no labels.
"""


def generate_query_aware_summary(webpage_content: str, user_query: str, detail_level: str) -> str:
    if not webpage_content or not webpage_content.strip():
        return "Summary unavailable."
    client = get_gemini_client()
    if client is None:
        return "Summary unavailable."

    content = webpage_content
    words = content.split()
    if len(words) > MAX_CONTENT_WORDS:
        content = " ".join(words[:MAX_CONTENT_WORDS])

    prompt = _build_prompt(content, user_query, detail_level)
    try:
        from google.genai import types
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=MAX_OUTPUT_TOKENS.get(detail_level, 300),
            ),
        )
        text = (response.text or "").strip() if response else ""
        return text if text else "Summary unavailable."
    except Exception as e:
        print(f"[MemoryLane] ✗ Gemini summarization failed: {e}")
        return "Summary unavailable."


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "MemoryLane backend is running"}


@app.post("/memory")
def save_memory(data: WebpageData):
    try:
        if not data.url or not data.title or not data.content:
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: url, title, content"
            )

        print(f"\n[MemoryLane] ═══ RECEIVED WEBPAGE ═══")
        print(f"[MemoryLane] Title: {data.title}")
        print(f"[MemoryLane] URL: {data.url}")
        print(f"[MemoryLane] Content length: {len(data.content)} characters")

        # id derived from the url so the same page always maps to the same record
        memory_id = data.url.replace("https://", "").replace("http://", "").replace("/", "_")
        memory_id = memory_id[:100]

        print(f"[MemoryLane] Converting content to embedding...")
        embedding = embedding_model.encode(
            data.content,
            convert_to_numpy=True
        ).tolist()
        print(f"[MemoryLane] ✓ Embedding generated (dimension: {len(embedding)})")

        timestamp = datetime.now().isoformat()

        # upsert, not add — revisiting a url updates the existing record
        # instead of erroring or creating a duplicate
        collection.upsert(
            ids=[memory_id],
            embeddings=[embedding],
            metadatas=[{
                "url": data.url,
                "title": data.title,
                "timestamp": timestamp
            }],
            documents=[data.content]
        )

        print(f"[MemoryLane] ✓ Stored in ChromaDB (upsert)")
        print(f"[MemoryLane] ✓ Memory ID: {memory_id}")

        try:
            bm25_index.upsert(memory_id, data.title, data.content)
            bm25_index.metadata[memory_id]["url"] = data.url
            print(f"[MemoryLane] ✓ BM25 index updated ({len(bm25_index.ids)} document(s) total)")
        except Exception as e:
            # same philosophy as the startup build: BM25 failing to update
            # shouldn't fail the save itself, just degrade future searches
            # for this memory back to semantic-only until the next rebuild
            print(f"[MemoryLane] ✗ Failed to update BM25 index for this memory: {e}")

        print(f"[MemoryLane] ═══════════════════════\n")

        return {
            "success": True,
            "message": "Memory stored successfully",
            "metadata": {
                "url": data.url,
                "title": data.title,
                "id": memory_id,
                "timestamp": timestamp
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[MemoryLane] ✗ Error storing memory: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to store memory: {str(e)}")


@app.post("/search")
def search_memory(query: SearchQuery):
    try:
        if not query.query or not query.query.strip():
            raise HTTPException(status_code=400, detail="Missing required field: query")

        if query.mode not in ("hybrid", "semantic", "bm25"):
            raise HTTPException(status_code=400, detail="mode must be one of: hybrid, semantic, bm25")

        count = collection.count()
        if count == 0:
            return {"query": query.query, "mode": query.mode, "results": []}

        # public API behavior preserved: still clamped 1-20
        num_results = max(1, min(query.num_results, 20))

        print(f"\n[MemoryLane] ═══ SEARCH ({query.mode}): \"{query.query}\" ═══")

        # retrieval only — no Gemini involved yet, per requirement that
        # summarization never influences what gets retrieved or how it's ranked
        ranked = hybrid_search(
            collection=collection,
            embedding_model=embedding_model,
            bm25_index=bm25_index,
            query_text=query.query,
            num_results=num_results,
            mode=query.mode,
            candidate_pool=DEFAULT_CANDIDATE_POOL,
            rrf_k=DEFAULT_RRF_K,
        )

        if not ranked:
            return {"query": query.query, "mode": query.mode, "results": []}

        # fetch metadata/documents for exactly the ids we're returning
        ids = [r["id"] for r in ranked]
        fetched = collection.get(ids=ids, include=["metadatas", "documents"])
        by_id = {
            fid: (meta, doc)
            for fid, meta, doc in zip(fetched["ids"], fetched["metadatas"], fetched["documents"])
        }

        detail_level = detect_length_category(query.query)
        results = []
        for rank, r in enumerate(ranked, start=1):
            metadata, document = by_id.get(r["id"], ({}, ""))
            metadata = metadata or {}

            summary = None
            if query.summarize:
                summary = generate_query_aware_summary(document or "", query.query, detail_level)

            # "similarity" keeps its original pre-hybrid meaning (semantic
            # cosine similarity) for backward compatibility — it is NOT the
            # ranking score when mode="hybrid"; that's hybrid_score, only
            # exposed when debug=True to avoid confusing normal callers
            # with three different, differently-scaled numbers
            semantic_score = r["semantic_score"]
            result = {
                "rank": rank,
                "id": r["id"],
                "title": metadata.get("title", "Untitled"),
                "url": metadata.get("url", ""),
                "timestamp": metadata.get("timestamp", ""),
                "similarity": round(semantic_score, 4) if semantic_score is not None else None,
                "summary": summary,
            }
            if query.debug:
                result["bm25_score"] = round(r["bm25_score"], 4) if r["bm25_score"] is not None else None
                result["semantic_score"] = round(semantic_score, 4) if semantic_score is not None else None
                result["hybrid_score"] = round(r["hybrid_score"], 6) if r["hybrid_score"] is not None else None
            results.append(result)

        print(f"[MemoryLane] ✓ Returning {len(results)} result(s)")
        print(f"[MemoryLane] ═══════════════════════\n")

        return {"query": query.query, "mode": query.mode, "detail_level": detail_level, "results": results}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[MemoryLane] ✗ Search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.on_event("startup")
def startup_event():
    print("\n" + "="*60)
    print("MemoryLane Backend Started")
    print("="*60)
    print(f"Embedding model: all-MiniLM-L6-v2")
    print(f"Vector database: ChromaDB (semantic retrieval)")
    print(f"Lexical retrieval: BM25 (rank_bm25), rebuilt from ChromaDB on startup")
    print(f"Search: hybrid (BM25 + semantic, fused with RRF) by default")
    print(f"Summarization: Gemini, after retrieval only")
    print(f"API endpoint: http://localhost:8000")
    print(f"Health check: http://localhost:8000/health")
    print(f"Save memory: POST http://localhost:8000/memory")
    print(f"Search memory: POST http://localhost:8000/search")
    print("="*60 + "\n")

# Run with: uvicorn backend.main:app --reload
# Test with: curl http://localhost:8000/health