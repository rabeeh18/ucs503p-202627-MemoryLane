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
from datetime import datetime

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


class WebpageData(BaseModel):
    # matches what the Tampermonkey script sends
    url: str
    title: str
    content: str


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


@app.on_event("startup")
def startup_event():
    print("\n" + "="*60)
    print("MemoryLane Backend Started")
    print("="*60)
    print(f"Embedding model: all-MiniLM-L6-v2")
    print(f"Vector database: ChromaDB (semantic retrieval)")
    print(f"Summarization: Gemini (query.py, at query time only — not loaded here)")
    print(f"API endpoint: http://localhost:8000")
    print(f"Health check: http://localhost:8000/health")
    print(f"Save memory: POST http://localhost:8000/memory")
    print("="*60 + "\n")

# Run with: uvicorn backend.main:app --reload
# Test with: curl http://localhost:8000/health