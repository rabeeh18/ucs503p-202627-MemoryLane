import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from backend.config import (
    BM25_WEIGHT, VECTOR_WEIGHT, DEFAULT_CANDIDATE_POOL, DEFAULT_TOP_K,
    RRF_K, PAGE_SECOND_CHUNK_WEIGHT, RERANK_ENABLED, RERANK_TOP_N,
)
from backend.embeddings import embed_query
from backend import rerank
from backend.solr_client import get_solr_client, unwrap_solr_value

logger = logging.getLogger(__name__)

# Shared pool so BM25 and (embed -> KNN) run concurrently without paying
# thread start-up cost on every request.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="retrieval")

SNIPPET_MAX_CHARS = 240

# Very common words that would otherwise match almost every sentence.
_SNIPPET_STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "had",
    "her", "was", "one", "our", "out", "has", "have", "his", "how", "its", "who",
    "did", "get", "him", "she", "too", "use", "that", "this", "with", "from",
    "they", "them", "then", "than", "what", "when", "where", "which", "about",
    "into", "your", "some", "there", "their", "were", "been", "does", "also",
}


def rrf_fuse(bm25_ids: list[str], knn_ids: list[str], k: int,
             w_bm25: float, w_knn: float) -> dict[str, float]:
    """Reciprocal Rank Fusion.

    score(chunk) = w_bm25 / (k + rank_bm25) + w_knn / (k + rank_knn), ranks start at 1.
    A chunk missing from one list gets nothing from it.
    """
    fused: dict[str, float] = {}
    for rank, doc_id in enumerate(bm25_ids, start=1):
        fused[doc_id] = fused.get(doc_id, 0.0) + w_bm25 / (k + rank)
    for rank, doc_id in enumerate(knn_ids, start=1):
        fused[doc_id] = fused.get(doc_id, 0.0) + w_knn / (k + rank)
    return fused


def group_by_webpage(candidates: list[dict], fused_scores: dict[str, float],
                     second_chunk_weight: float = None) -> list[dict]:
    """Group chunks by page_id.

    Page score = best chunk score + second_chunk_weight * second-best chunk score
    (0 if the page has only one candidate chunk). The best chunk supplies the
    result's metadata and its text (used for the snippet).

    Returns list of webpage-level results with:
    - page_id, id (best chunk id), url, title, domain, timestamp, text
    - fused_score (page score), bm25_rank, knn_rank (from best chunk)
    """
    if second_chunk_weight is None:
        second_chunk_weight = PAGE_SECOND_CHUNK_WEIGHT

    pages: dict[str, list[tuple[float, dict]]] = {}
    for doc in candidates:
        doc_id = unwrap_solr_value(doc["id"], "id")
        page_id = unwrap_solr_value(doc.get("page_id", ""), "page_id")
        score = fused_scores.get(doc["id"], fused_scores.get(doc_id, 0.0))
        pages.setdefault(page_id, []).append((score, doc))

    results = []
    for page_id, scored in pages.items():
        scored.sort(key=lambda pair: pair[0], reverse=True)
        best_score, best = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        results.append({
            "page_id": page_id,
            "id": unwrap_solr_value(best["id"], "id"),
            "url": unwrap_solr_value(best.get("url", ""), "url"),
            "title": unwrap_solr_value(best.get("title", ""), "title"),
            "domain": unwrap_solr_value(best.get("domain", ""), "domain"),
            "timestamp": unwrap_solr_value(best.get("timestamp", ""), "timestamp"),
            "text": unwrap_solr_value(best.get("text", ""), "text") or "",
            "fused_score": best_score + second_chunk_weight * second_score,
            "bm25_rank": best.get("_bm25_rank"),
            "knn_rank": best.get("_knn_rank"),
        })

    results.sort(key=lambda x: x["fused_score"], reverse=True)
    return results


def _query_terms(query: str) -> list[str]:
    terms = []
    for term in re.findall(r"\w+", (query or "").lower()):
        if len(term) >= 3 and term not in _SNIPPET_STOPWORDS and term not in terms:
            terms.append(term)
    return terms


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p and p.strip()]


def _trim_at_word(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    space = cut.rfind(" ")
    if space > max_chars // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:-") + "…"


def build_snippet(text: str, query: str, max_chars: int = SNIPPET_MAX_CHARS) -> str | None:
    """Plain-text snippet from a chunk: the first sentence containing a query term
    (prefix match, so "learn" matches "learning"), else the first sentence.
    Trimmed to about max_chars at a word boundary, with … where text was cut.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return None

    terms = _query_terms(query)
    chosen = sentences[0]
    match_at = -1
    for sentence in sentences:
        for m in re.finditer(r"\w+", sentence.lower()):
            if any(m.group().startswith(t) for t in terms):
                chosen, match_at = sentence, m.start()
                break
        if match_at >= 0:
            break

    prefix = ""
    # Long sentence with the match far in: start shortly before the match.
    if match_at > max_chars - 60:
        start = max(0, match_at - 60)
        space = chosen.find(" ", start)
        if 0 <= space < match_at:
            start = space + 1
        chosen = chosen[start:]
        prefix = "…"

    return prefix + _trim_at_word(chosen, max_chars)


@lru_cache(maxsize=1024)
def _cached_query_embedding(query: str) -> tuple[float, ...]:
    return tuple(embed_query(query))


def _timed_bm25(solr, query: str, rows: int):
    start = time.perf_counter()
    docs = solr.bm25_search(query, rows=rows)
    return docs, (time.perf_counter() - start) * 1000


def _timed_knn(solr, query: str, k: int):
    start = time.perf_counter()
    vector = list(_cached_query_embedding(query))
    embedded = time.perf_counter()
    docs = solr.knn_search(vector, k=k)
    done = time.perf_counter()
    return docs, (embedded - start) * 1000, (done - embedded) * 1000


def _rerank(query: str, candidates_map: dict, fused: dict[str, float],
            grouped: list[dict]) -> list[dict]:
    """Cross-encoder rerank of the top RERANK_TOP_N chunks after RRF.

    Pages are aggregated from the reranker scores (best + weighted second-best).
    Pages with no chunk in the top N follow in their RRF order.
    """
    top_ids = sorted(fused, key=fused.get, reverse=True)[:RERANK_TOP_N]
    top_docs = [candidates_map[doc_id] for doc_id in top_ids if doc_id in candidates_map]
    passages = [
        f"{unwrap_solr_value(d.get('title', ''), 'title')}\n\n{unwrap_solr_value(d.get('text', ''), 'text')}"
        for d in top_docs
    ]
    scores = rerank.rerank_scores(query, passages)
    rerank_by_id = {d["id"]: s for d, s in zip(top_docs, scores)}

    reranked = group_by_webpage(top_docs, rerank_by_id)
    for page in reranked:
        page["rerank_score"] = page["fused_score"]
    seen = {page["page_id"] for page in reranked}
    return reranked + [page for page in grouped if page["page_id"] not in seen]


def hybrid_search(query: str, top_k: int = None, candidate_pool: int = None,
                  timings: dict | None = None) -> list[dict]:
    """Full hybrid search pipeline.

    Steps:
    1. BM25 search and (embed query -> KNN search), concurrently
    2. Reciprocal Rank Fusion of the two ranked chunk lists
    3. Group by webpage (best chunk + weighted second-best chunk)
    4. Optionally rerank the top chunks with a cross-encoder (RERANK_ENABLED)
    5. Return top-K with snippets

    If `timings` is given, it is filled with per-stage durations in ms.
    Returns list of webpage-level results.
    """
    top_k = top_k or DEFAULT_TOP_K
    candidate_pool = candidate_pool or DEFAULT_CANDIDATE_POOL
    total_start = time.perf_counter()

    solr = get_solr_client()

    bm25_future = _executor.submit(_timed_bm25, solr, query, candidate_pool)
    knn_future = _executor.submit(_timed_knn, solr, query, candidate_pool)
    bm25_docs, bm25_ms = bm25_future.result()
    knn_docs, embed_ms, knn_ms = knn_future.result()
    logger.info(f"BM25 returned {len(bm25_docs)} candidates, KNN returned {len(knn_docs)}")

    fuse_start = time.perf_counter()

    # Build candidate map (dedup by id), remembering each chunk's rank per list
    candidates_map = {}
    for rank, doc in enumerate(bm25_docs, start=1):
        doc["_bm25_rank"] = rank
        doc["_knn_rank"] = None
        candidates_map[doc["id"]] = doc
    for rank, doc in enumerate(knn_docs, start=1):
        if doc["id"] in candidates_map:
            candidates_map[doc["id"]]["_knn_rank"] = rank
        else:
            doc["_bm25_rank"] = None
            doc["_knn_rank"] = rank
            candidates_map[doc["id"]] = doc

    fused = rrf_fuse(
        [doc["id"] for doc in bm25_docs],
        [doc["id"] for doc in knn_docs],
        k=RRF_K, w_bm25=BM25_WEIGHT, w_knn=VECTOR_WEIGHT,
    )

    grouped = group_by_webpage(list(candidates_map.values()), fused)
    fuse_ms = (time.perf_counter() - fuse_start) * 1000

    rerank_ms = 0.0
    if RERANK_ENABLED and candidates_map:
        rerank_start = time.perf_counter()
        grouped = _rerank(query, candidates_map, fused, grouped)
        rerank_ms = (time.perf_counter() - rerank_start) * 1000

    results = grouped[:top_k]

    for i, result in enumerate(results):
        result["rank"] = i + 1
        result["snippet"] = build_snippet(result.get("text", ""), query)

    stage_timings = {
        "embed_ms": round(embed_ms, 1),
        "bm25_ms": round(bm25_ms, 1),
        "knn_ms": round(knn_ms, 1),
        "fuse_ms": round(fuse_ms, 1),
        "rerank_ms": round(rerank_ms, 1),
        "total_ms": round((time.perf_counter() - total_start) * 1000, 1),
    }
    logger.info("Search timings: " + " ".join(f"{k}={v}" for k, v in stage_timings.items()))
    if timings is not None:
        timings.update(stage_timings)

    logger.info(f"Returning {len(results)} results")
    return results
