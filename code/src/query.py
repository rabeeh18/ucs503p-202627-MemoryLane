#!/usr/bin/env python3
"""
MemoryLane query CLI.

    query -> optimize query -> embed
        -> semantic search (ChromaDB) + keyword search (BM25) over chunks
        -> merge candidates -> rerank (cross-encoder)
        -> adaptive cutoff -> group chunks back into webpages
        -> display webpages (no summary yet)
        -> user picks a result -> summarize just that result's best chunk(s)

Usage:
    python query.py "that article about PPO clipping"
    python query.py "quickly remind me about the OS memory article"
    python query.py "give me a detailed summary of that internship posting" --no-prompt
"""

import sys
import os
import re
import math
import argparse
from datetime import datetime

import numpy as np
from sentence_transformers import SentenceTransformer, CrossEncoder
from rank_bm25 import BM25Okapi
import chromadb

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # fine if GEMINI_API_KEY is set some other way

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
RERANKER_MODEL = os.environ.get("RERANKER_MODEL", "BAAI/bge-reranker-base")

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
    collection = chroma_client.get_collection(name="memorylane_chunks")
    print(f"[MemoryLane] ✓ Connected to ChromaDB")
    print(f"[MemoryLane] Database path: {db_path}\n")
except Exception as e:
    print(f"[MemoryLane] ✗ Failed to connect to ChromaDB: {e}")
    print("[MemoryLane] Make sure the database exists (save a webpage first)")
    sys.exit(1)


# --- gemini client (used for both query optimization and on-demand summaries) ---
# lazy + cached so a missing key doesn't crash retrieval-only usage, and we
# don't reconnect on every call

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


# --- reranker (loaded lazily — it's a real model download, only pay for
# it if the user actually runs a query) ---

_reranker = None
_reranker_init_error = None


def get_reranker():
    global _reranker, _reranker_init_error

    if _reranker is not None or _reranker_init_error is not None:
        return _reranker

    try:
        print(f"[MemoryLane] Loading reranker '{RERANKER_MODEL}' (first run downloads it)...")
        _reranker = CrossEncoder(RERANKER_MODEL)
        print("[MemoryLane] ✓ Reranker loaded")
    except Exception as e:
        _reranker_init_error = str(e)
        print(f"[MemoryLane] ✗ Failed to load reranker: {e}")
        _reranker = None

    return _reranker


# --- query optimization ---
# users describe memories vaguely ("that robot thing avoiding obstacles").
# ask Gemini to expand that into a keyword-dense phrase before embedding /
# BM25, so both retrieval methods have more to match against. Falls back
# to the raw query untouched if Gemini isn't available — optimization is
# a quality boost, not a requirement.

def optimize_query(raw_query: str) -> str:
    client = get_gemini_client()
    if client is None:
        return raw_query

    prompt = f"""Expand this vague memory/search query into a short, keyword-dense
phrase that captures the likely topic, so it matches better against a
search index. Do not answer the query. Do not add punctuation or
commentary. Return ONLY the expanded phrase, nothing else.

QUERY: "{raw_query}"
"""
    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        expanded = (response.text or "").strip() if response else ""
        return expanded if expanded else raw_query
    except Exception as e:
        print(f"[MemoryLane] ⚠ Query optimization failed ({e}); using raw query.")
        return raw_query


# --- detail-level detection (unchanged idea: keyword heuristic on the
# ORIGINAL query, not the optimized one, since "briefly"/"detailed" are
# about output length, not topic) ---

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


def detect_length_category(query_text: str) -> str:
    text = query_text.lower()
    for pattern in LONG_PATTERNS:
        if re.search(pattern, text):
            return "LONG"
    for pattern in SHORT_PATTERNS:
        if re.search(pattern, text):
            return "SHORT"
    return "MEDIUM"


# --- on-demand, chunk-scoped summarization ---
# only ever called when the user explicitly asks for a summary, and only
# ever given the specific chunk(s) that matched — never the whole page —
# which is most of the API cost savings versus summarizing every result
# up front on the full page text.

MAX_CONTENT_WORDS = 1500  # generous for 1-2 chunks; a real cap, not expected to trigger often


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
            print("[MemoryLane] ⚠ Gemini returned an empty response.")
            return "Summary unavailable."
        return text
    except Exception as e:
        print(f"[MemoryLane] ✗ Gemini summarization failed: {e}")
        return "Summary unavailable."


# --- keyword index (BM25) over chunks ---
# rebuilt fresh each run from whatever's currently in ChromaDB. Simple,
# always in sync with the vector store, fine at personal-history scale.
# ChromaDB stays the vector database; this is a separate, lightweight
# keyword layer next to it, not a replacement for it.

def tokenize(text: str):
    return re.findall(r"[a-z0-9]+", text.lower())


def build_chunk_corpus():
    all_data = collection.get(include=["documents", "metadatas"])
    ids = all_data.get("ids", [])
    docs = all_data.get("documents", [])
    metas = all_data.get("metadatas", [])

    corpus = [
        {"id": ids[i], "text": docs[i], "metadata": metas[i]}
        for i in range(len(ids))
    ]
    tokenized = [tokenize(c["text"]) for c in corpus]
    bm25 = BM25Okapi(tokenized) if corpus else None
    return bm25, corpus


# --- hybrid retrieval: semantic (ChromaDB) + keyword (BM25) candidates,
# merged into one pool for the reranker to sort out ---

def hybrid_candidates(query_text: str, query_embedding, bm25, corpus, pool_size=40):
    candidates = {}

    semantic = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(pool_size, max(collection.count(), 1)),
        include=["documents", "metadatas", "distances"],
    )
    for cid, doc, meta in zip(semantic["ids"][0], semantic["documents"][0], semantic["metadatas"][0]):
        candidates[cid] = {"id": cid, "text": doc, "metadata": meta}

    if bm25 is not None and corpus:
        tokenized_query = tokenize(query_text)
        scores = bm25.get_scores(tokenized_query)
        top_indices = np.argsort(scores)[::-1][:pool_size]
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            entry = corpus[idx]
            candidates.setdefault(entry["id"], {"id": entry["id"], "text": entry["text"], "metadata": entry["metadata"]})

    return list(candidates.values())


# --- reranking ---
# bge-reranker-base gives a raw logit per (query, chunk) pair; squash it
# through a sigmoid to get something readable as a 0-1 relevance score.

def rerank_candidates(query_text: str, candidates: list):
    if not candidates:
        return []

    reranker = get_reranker()
    if reranker is None:
        # no reranker available — fall back to candidate order as-is
        for c in candidates:
            c["score"] = 0.5
        return candidates

    pairs = [(query_text, c["text"]) for c in candidates]
    raw_scores = reranker.predict(pairs)
    scores = 1 / (1 + np.exp(-np.array(raw_scores)))

    for c, s in zip(candidates, scores):
        c["score"] = float(s)

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


# --- adaptive cutoff ---
# instead of a fixed top-k, look for the first big relevance drop and cut
# there. If scores decline gently with no sharp elbow, keep more results
# (capped at max_results so a long, flat tail doesn't dump everything).

def adaptive_cutoff(scores: list, min_results=1, max_results=20, min_gap=0.05, gap_ratio=2.0):
    if not scores:
        return 0

    n = min(len(scores), max_results)
    trimmed = scores[:n]

    if n <= min_results:
        return n

    diffs = [trimmed[i] - trimmed[i + 1] for i in range(n - 1)]
    avg_diff = sum(diffs) / len(diffs) if diffs else 0

    for i in range(min_results - 1, n - 1):
        gap = diffs[i]
        if gap >= min_gap and gap >= avg_diff * gap_ratio:
            return i + 1

    return n  # no clear elbow — keep the whole (capped) list


# --- group chunks back into webpages ---
# candidates are already sorted best-first by the reranker, so the first
# time we see a webpage_id its score IS the webpage's max chunk score —
# no averaging, no re-sorting needed.

def group_chunks_to_webpages(scored_chunks: list):
    webpages = {}
    order = []

    for chunk in scored_chunks:
        meta = chunk["metadata"]
        wid = meta.get("webpage_id")
        if wid not in webpages:
            webpages[wid] = {
                "webpage_id": wid,
                "title": meta.get("title", "Untitled"),
                "url": meta.get("url", "Unknown"),
                "timestamp": meta.get("timestamp"),
                "best_score": chunk["score"],
                "chunks": [],
            }
            order.append(wid)
        webpages[wid]["chunks"].append({"text": chunk["text"], "score": chunk["score"]})

    for wid in webpages:
        webpages[wid]["chunks"].sort(key=lambda c: c["score"], reverse=True)

    return [webpages[wid] for wid in order]


# --- human-readable relative time ---

def humanize_timestamp(iso_ts: str) -> str:
    if not iso_ts:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(iso_ts)
    except Exception:
        return iso_ts

    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    delta = now - dt
    days = delta.days

    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 30:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    if days < 365:
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"


# --- top-level search: optimize -> hybrid retrieve -> rerank -> cutoff -> group ---

def search_memories(raw_query: str, pool_size=40, debug=False):
    if collection.count() == 0:
        print("[MemoryLane] ✗ No memories stored yet.")
        print("[MemoryLane] Save some webpages first using the Tampermonkey script.")
        return raw_query, raw_query, []

    optimized_query = optimize_query(raw_query)
    if debug and optimized_query != raw_query:
        print(f"[MemoryLane] [debug] optimized query: \"{optimized_query}\"")

    query_embedding = embedding_model.encode(optimized_query, convert_to_numpy=True).tolist()

    bm25, corpus = build_chunk_corpus()
    candidates = hybrid_candidates(optimized_query, query_embedding, bm25, corpus, pool_size=pool_size)

    if debug:
        print(f"[MemoryLane] [debug] {len(candidates)} candidate chunk(s) before reranking")

    reranked = rerank_candidates(optimized_query, candidates)
    scores = [c["score"] for c in reranked]
    cutoff = adaptive_cutoff(scores)

    if debug:
        print(f"[MemoryLane] [debug] adaptive cutoff kept {cutoff}/{len(reranked)} chunk(s)")

    survivors = reranked[:cutoff]
    webpages = group_chunks_to_webpages(survivors)

    return raw_query, optimized_query, webpages


# --- display ---

def display_results(raw_query: str, webpages: list, debug=False):
    print("\n" + "=" * 80)
    print("MEMORYLANE SEARCH RESULTS")
    print("=" * 80)
    print(f"Query: \"{raw_query}\"")
    print(f"Results: {len(webpages)}")
    print("=" * 80 + "\n")

    if not webpages:
        print("No matching memories found.\n")
        return

    for i, page in enumerate(webpages, 1):
        print(f"{i}. {page['title']}")
        print()
        print("   URL:")
        print(f"   {page['url']}")
        print()
        print(f"   Visited: {humanize_timestamp(page['timestamp'])}")

        if debug:
            print(f"   [debug] best chunk score: {page['best_score']:.4f}")
            print(f"   [debug] matching chunks:  {len(page['chunks'])}")
            print(f"   [debug] webpage_id:       {page['webpage_id']}")

        print()
        print("   [Generate Summary] — pick this result's number to see one")
        print()

    print("=" * 80 + "\n")


# --- on-demand summary loop ---
# the CLI equivalent of clicking "[Generate Summary]" on a result: only
# the chosen webpage's top chunk(s) go to Gemini, only when asked.

def run_summary_prompt(raw_query: str, webpages: list):
    detail_level = detect_length_category(raw_query)

    while True:
        choice = input("Generate summary for result number (or Enter to quit): ").strip()
        if not choice:
            return

        if not choice.isdigit() or not (1 <= int(choice) <= len(webpages)):
            print(f"Enter a number between 1 and {len(webpages)}, or press Enter to quit.")
            continue

        page = webpages[int(choice) - 1]
        # top 1-2 chunks only — not the whole page — keeps the Gemini call small
        top_chunks = [c["text"] for c in page["chunks"][:2]]
        chunk_text = "\n\n".join(top_chunks)

        print(f"\nGenerating summary for: {page['title']}...")
        summary = generate_query_aware_summary(chunk_text, raw_query, detail_level)
        print("\nSummary:")
        for line in summary.split("\n"):
            print(f"  {line}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Search your MemoryLane memories using natural language",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python query.py "that article about PPO clipping"
  python query.py "quickly remind me about the database internship posting"
  python query.py "give me a detailed summary of that OS memory article" --no-prompt
        """
    )

    parser.add_argument("query", nargs="?", help="Natural language search query")
    parser.add_argument("--candidates", type=int, default=40,
                        help="Candidate chunk pool size before reranking (default: 40)")
    parser.add_argument("--debug", action="store_true",
                        help="Show optimized query, candidate counts, and per-result scores")
    parser.add_argument("--no-prompt", action="store_true",
                        help="Skip the interactive 'generate summary' prompt after results")

    args = parser.parse_args()

    if not args.query:
        print("[MemoryLane] No query provided.")
        print("\nUsage: python query.py \"your search query\"")
        print("Example: python query.py \"that article about PPO clipping\"")
        sys.exit(1)

    print("\n" + "=" * 80)
    print("MEMORYLANE SEARCH")
    print("=" * 80 + "\n")

    raw_query, optimized_query, webpages = search_memories(args.query, pool_size=args.candidates, debug=args.debug)
    display_results(raw_query, webpages, debug=args.debug)

    if webpages and not args.no_prompt:
        run_summary_prompt(raw_query, webpages)


if __name__ == "__main__":
    main()
