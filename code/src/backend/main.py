# MemoryLane backend — receives a webpage from the userscript, splits it
# into chunks, embeds each chunk, stores them in ChromaDB. The user still
# only ever sees whole webpages later (query.py groups chunks back up) —
# chunking here is purely a retrieval-quality optimization, not a new
# kind of memory.
#
# YouTube watch pages are a special case: the userscript sends no page
# content for these (the player UI has nothing worth extracting), and
# this file fetches the actual video transcript instead, so a YouTube
# video is remembered by what's said in it, not by its title alone.

import re
from urllib.parse import urlparse, parse_qs
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
import os

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
    YOUTUBE_TRANSCRIPTS_AVAILABLE = True
except ImportError:
    YOUTUBE_TRANSCRIPTS_AVAILABLE = False

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
    # NOTE: this collection now holds CHUNKS, not whole webpages. Each
    # chunk is its own vector so a query can hit the one paragraph that
    # actually matters instead of a blurred whole-page average.
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
    # matches what the Tampermonkey script sends. content can be empty
    # for YouTube watch pages — the userscript deliberately skips
    # Readability there and lets this file fetch the transcript instead.
    url: str
    title: str
    content: str = ""


# --- YouTube transcript fetching ---
# The userscript recognizes youtube.com/watch and /shorts/ pages and sends
# {url, title, content: ""} for them rather than running Readability on
# the player UI. This is where the actual video content comes from.

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def is_youtube_watch_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    host = parsed.netloc.lower()
    if host not in YOUTUBE_HOSTS:
        return False

    if host == "youtu.be":
        return len(parsed.path.strip("/")) > 0

    return parsed.path.startswith("/watch") or parsed.path.startswith("/shorts/")


def extract_youtube_video_id(url: str):
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
        return video_id or None

    if parsed.path.startswith("/shorts/"):
        video_id = parsed.path[len("/shorts/"):].split("/")[0]
        return video_id or None

    query = parse_qs(parsed.query)
    video_ids = query.get("v")
    return video_ids[0] if video_ids else None


def fetch_youtube_transcript(video_id: str):
    """Returns the transcript as plain text, or None if unavailable."""
    if not YOUTUBE_TRANSCRIPTS_AVAILABLE:
        print("[MemoryLane] ✗ youtube-transcript-api not installed — cannot fetch transcript")
        return None

    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id, languages=("en",))
        text = " ".join(snippet.text for snippet in transcript if snippet.text)
        return text.strip() or None
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
        print(f"[MemoryLane] No transcript available for video {video_id}: {e}")
        return None
    except Exception as e:
        print(f"[MemoryLane] ✗ Transcript fetch failed for {video_id}: {e}")
        return None


# --- chunking ---
# Split a webpage's extracted text into ~300-500 word pieces. Paragraph
# boundaries first (so we don't cut mid-thought); if the page has no
# paragraph breaks at all, fall back to splitting on sentences. Small
# leftover paragraphs get folded into the running chunk instead of
# becoming their own tiny, low-signal chunk.
TARGET_MIN_WORDS = 300
TARGET_MAX_WORDS = 500


def chunk_webpage_content(content: str, target_min=TARGET_MIN_WORDS, target_max=TARGET_MAX_WORDS):
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content.strip()) if p.strip()]

    if len(paragraphs) <= 1:
        # no real paragraph structure (this is also the shape a YouTube
        # transcript comes in as — one long run of text) — split on
        # sentence boundaries instead
        paragraphs = [s.strip() for s in re.split(r"(?<=[.!?])\s+", content.strip()) if s.strip()]

    chunks = []
    buffer_words = []

    for para in paragraphs:
        para_words = para.split()

        if buffer_words and len(buffer_words) + len(para_words) > target_max:
            chunks.append(" ".join(buffer_words))
            buffer_words = []

        buffer_words.extend(para_words)

        while len(buffer_words) > target_max:
            chunks.append(" ".join(buffer_words[:target_max]))
            buffer_words = buffer_words[target_max:]

        if len(buffer_words) >= target_min:
            chunks.append(" ".join(buffer_words))
            buffer_words = []

    if buffer_words:
        if chunks and len(buffer_words) < 50:
            chunks[-1] = chunks[-1] + " " + " ".join(buffer_words)
        else:
            chunks.append(" ".join(buffer_words))

    return chunks if chunks else [content.strip()]


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "MemoryLane backend is running"}


@app.post("/memory")
def save_memory(data: WebpageData):
    try:
        if not data.url or not data.title:
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: url, title"
            )

        content = data.content

        # a YouTube video's real content is what's said in it, not the
        # player UI — fetch the transcript regardless of what (if
        # anything) the userscript sent as content
        if is_youtube_watch_url(data.url):
            video_id = extract_youtube_video_id(data.url)
            if video_id:
                print(f"[MemoryLane] YouTube video detected ({video_id}) — fetching transcript...")
                transcript = fetch_youtube_transcript(video_id)
                if transcript:
                    content = transcript
                    print(f"[MemoryLane] ✓ Transcript fetched ({len(transcript)} characters)")
                elif not content:
                    raise HTTPException(
                        status_code=400,
                        detail="Could not fetch a transcript for this video (none available, and no fallback content was sent)"
                    )
            elif not content:
                raise HTTPException(status_code=400, detail="Could not determine YouTube video ID from URL")

        if not content:
            raise HTTPException(status_code=400, detail="Missing required field: content")

        print(f"\n[MemoryLane] ═══ RECEIVED WEBPAGE ═══")
        print(f"[MemoryLane] Title: {data.title}")
        print(f"[MemoryLane] URL: {data.url}")
        print(f"[MemoryLane] Content length: {len(content)} characters")

        # webpage_id derived from the url so the same page always maps to
        # the same group of chunks, no matter how many times it's re-saved
        webpage_id = data.url.replace("https://", "").replace("http://", "").replace("/", "_")
        webpage_id = webpage_id[:100]
        domain = urlparse(data.url).netloc

        chunks = chunk_webpage_content(content)
        print(f"[MemoryLane] Split into {len(chunks)} chunk(s)")

        timestamp = datetime.now().isoformat()

        print(f"[MemoryLane] Embedding {len(chunks)} chunk(s)...")
        embeddings = embedding_model.encode(chunks, convert_to_numpy=True).tolist()

        # revisiting a url should update its chunks, not pile up old ones
        # next to new ones — clear out anything already stored for this
        # webpage before writing the fresh set
        collection.delete(where={"webpage_id": webpage_id})

        chunk_ids = [f"{webpage_id}::chunk::{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "webpage_id": webpage_id,
                "url": data.url,
                "title": data.title,
                "chunk_id": i,
                "total_chunks": len(chunks),
                "timestamp": timestamp,
                "domain": domain,
            }
            for i in range(len(chunks))
        ]

        collection.upsert(
            ids=chunk_ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=chunks,
        )

        print(f"[MemoryLane] ✓ Stored {len(chunks)} chunk(s) in ChromaDB")
        print(f"[MemoryLane] ✓ Webpage ID: {webpage_id}")
        print(f"[MemoryLane] ═══════════════════════\n")

        return {
            "success": True,
            "message": "Memory stored successfully",
            "metadata": {
                "url": data.url,
                "title": data.title,
                "id": webpage_id,
                "chunks": len(chunks),
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
    print(f"Vector database: ChromaDB (chunk-level semantic retrieval)")
    print(f"Chunk size target: {TARGET_MIN_WORDS}-{TARGET_MAX_WORDS} words")
    print(f"YouTube transcripts: {'enabled' if YOUTUBE_TRANSCRIPTS_AVAILABLE else 'disabled (pip install youtube-transcript-api)'}")
    print(f"Summarization: Gemini (query.py, on demand only — not loaded here)")
    print(f"API endpoint: http://localhost:8000")
    print(f"Health check: http://localhost:8000/health")
    print(f"Save memory: POST http://localhost:8000/memory")
    print("="*60 + "\n")

# Run with: uvicorn backend.main:app --reload
# Test with: curl http://localhost:8000/health
# New dependency: pip install youtube-transcript-api
