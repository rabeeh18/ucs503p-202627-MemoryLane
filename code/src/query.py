#!/usr/bin/env python3
"""
MemoryLane query CLI.

    query text -> MiniLM embedding -> ChromaDB search -> top matches
    for each match: original page text -> Gemini -> query-focused summary

Usage:
    python query.py "that article about PPO clipping"
    python query.py "quickly remind me about the OS memory article"
    python query.py "give me a detailed summary of that internship posting" --results 3
"""

import sys
import os
import re
import argparse
from sentence_transformers import SentenceTransformer
import chromadb

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # fine if GEMINI_API_KEY is set some other way

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

print("[MemoryLane] Loading embedding model 'all-MiniLM-L6-v2'...")
try:
    embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    print("[MemoryLane] ✓ Model loaded successfully\n")
except Exception as e:
    print(f"[MemoryLane] ✗ Failed to load model: {e}")
    sys.exit(1)

print("[MemoryLane] Connecting to ChromaDB...")
try:
    db_path = "./chroma_db"

    if not os.path.exists(db_path):
        print(f"[MemoryLane] ✗ Database not found at {db_path}")
        print("[MemoryLane] Have you saved any webpages yet?")
        sys.exit(1)

    chroma_client = chromadb.PersistentClient(path=db_path)
    collection = chroma_client.get_collection(name="memorylane")
    print(f"[MemoryLane] ✓ Connected to ChromaDB")
    print(f"[MemoryLane] Database path: {db_path}\n")
except Exception as e:
    print(f"[MemoryLane] ✗ Failed to connect to ChromaDB: {e}")
    print("[MemoryLane] Make sure the database exists (save a webpage first)")
    sys.exit(1)


# lazy client so a missing API key doesn't crash retrieval-only usage
_gemini_client = None
_gemini_init_error = None


def get_gemini_client():
    global _gemini_client, _gemini_init_error

    if _gemini_client is not None or _gemini_init_error is not None:
        return _gemini_client

    if not GEMINI_API_KEY:
        _gemini_init_error = "GEMINI_API_KEY is not set in the environment / .env file"
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


# crude keyword-based detail detection — good enough for "briefly" vs "in depth"
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

MAX_OUTPUT_TOKENS = {
    "SHORT": 120,
    "MEDIUM": 300,
    "LONG": 600,
}


def detect_length_category(query_text: str) -> str:
    text = query_text.lower()
    for pattern in LONG_PATTERNS:
        if re.search(pattern, text):
            return "LONG"
    for pattern in SHORT_PATTERNS:
        if re.search(pattern, text):
            return "SHORT"
    return "MEDIUM"


# cap so we don't ship a huge page into every prompt
MAX_CONTENT_WORDS = 4000


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
        if not text:
            print("[MemoryLane] ⚠ Gemini returned an empty response for this memory.")
            return "Summary unavailable."

        return text

    except Exception as e:
        # covers rate limits, network errors, bad responses — never crash the query for this
        print(f"[MemoryLane] ✗ Gemini summarization failed: {e}")
        return "Summary unavailable."


def search_memories(query_text, num_results=5):
    try:
        count = collection.count()
        if count == 0:
            print("[MemoryLane] ✗ No memories stored yet.")
            print("[MemoryLane] Save some webpages first using the Tampermonkey script.")
            return []

        print(f"[MemoryLane] Searching {count} stored memories...\n")

        print(f"[MemoryLane] Query: \"{query_text}\"")
        print("[MemoryLane] Converting query to embedding...")
        query_embedding = embedding_model.encode(
            query_text,
            convert_to_numpy=True
        ).tolist()
        print(f"[MemoryLane] ✓ Query embedding generated (dimension: {len(query_embedding)})\n")

        print("[MemoryLane] Searching ChromaDB for similar embeddings...")
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=num_results,
            include=["metadatas", "distances", "documents"]
        )

        if not results["ids"][0]:
            print("[MemoryLane] ✗ No matching memories found.")
            return []

        print(f"[MemoryLane] ✓ Found {len(results['ids'][0])} matching memories\n")

        memories = []
        for i, (memory_id, distance, metadata, document) in enumerate(zip(
            results["ids"][0],
            results["distances"][0],
            results["metadatas"][0],
            results["documents"][0]
        )):
            # kept for ranking/debug only — never shown to the user directly
            similarity_score = max(0, 1 - distance)

            memories.append({
                "rank": i + 1,
                "title": metadata.get("title", "Untitled"),
                "url": metadata.get("url", "Unknown"),
                "timestamp": metadata.get("timestamp", "Unknown"),
                "similarity": similarity_score,
                "distance": distance,
                "id": memory_id,
                "document": document,
            })

        return memories

    except Exception as e:
        print(f"[MemoryLane] ✗ Search error: {e}")
        import traceback
        traceback.print_exc()
        return []


def display_results(query_text, memories, debug=False):
    print("\n" + "=" * 80)
    print("MEMORYLANE SEARCH RESULTS")
    print("=" * 80)
    print(f"Query: \"{query_text}\"")
    print(f"Results: {len(memories)}")
    print("=" * 80 + "\n")

    if not memories:
        print("No matching memories found.\n")
        return

    detail_level = detect_length_category(query_text)

    for memory in memories:
        print(f"{memory['rank']}. {memory['title']}")
        print()
        print("   URL:")
        print(f"   {memory['url']}")
        print()

        summary = generate_query_aware_summary(
            memory.get("document") or "",
            query_text,
            detail_level
        )
        print("   Summary:")
        for line in summary.split("\n"):
            print(f"   {line}")

        if debug:
            print()
            print(f"   [debug] similarity:   {memory['similarity']:.2%}")
            print(f"   [debug] distance:     {memory['distance']:.4f}")
            print(f"   [debug] memory_id:    {memory['id']}")
            print(f"   [debug] saved:        {memory['timestamp']}")
            print(f"   [debug] detail_level: {detail_level}")

        print()

    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Search your MemoryLane memories using natural language",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python query.py "that article about PPO clipping"
  python query.py "quickly remind me about the database internship posting"
  python query.py "give me a detailed summary of that OS memory article" --results 3
        """
    )

    parser.add_argument("query", nargs="?", help="Natural language search query")
    parser.add_argument("-n", "--results", type=int, default=5, help="Number of results to display (default: 5)")
    parser.add_argument("--debug", action="store_true", help="Show similarity/distance/id/detail level")

    args = parser.parse_args()

    if not args.query:
        print("[MemoryLane] No query provided.")
        print("\nUsage: python query.py \"your search query\"")
        print("Example: python query.py \"that article about PPO clipping\"")
        sys.exit(1)

    print("\n" + "=" * 80)
    print("MEMORYLANE SEARCH")
    print("=" * 80 + "\n")

    memories = search_memories(args.query, num_results=args.results)
    display_results(args.query, memories, debug=args.debug)


if __name__ == "__main__":
    main()