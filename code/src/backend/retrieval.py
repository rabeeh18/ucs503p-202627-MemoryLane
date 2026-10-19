import logging
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from backend.config import (
    BM25_WEIGHT, VECTOR_WEIGHT, DEFAULT_CANDIDATE_POOL, DEFAULT_TOP_K,
    RRF_K, PAGE_SECOND_CHUNK_WEIGHT, RERANK_ENABLED, RERANK_TOP_N, MIN_VECTOR_SIMILARITY,
)
from backend.embeddings import embed_passages, embed_query
from backend import rerank
from backend.snippets import SentenceEmbeddingCache, build_snippet, build_snippets  # noqa: F401
from backend.solr_client import SolrClient, get_solr_client, unwrap_solr_value

logger = logging.getLogger(__name__)

# Shared pool so BM25 and (embed -> KNN) run concurrently without paying
# thread start-up cost on every request.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="retrieval")

# Embeddings of candidate snippet sentences (for picking the best sentence).
_sentence_embeddings = SentenceEmbeddingCache(lambda texts: embed_passages(texts))


def knn_score_to_cosine(score: float) -> float:
    """Solr's cosine DenseVectorField scores (1 + cos) / 2; undo that."""
    return 2.0 * float(score) - 1.0

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
    - page_id, id (best chunk id), url, title, domain, timestamp, text, description
    - fused_score (page score), bm25_rank, knn_rank (from best chunk)
    - bm25_match (any chunk matched BM25), vector_similarity (best chunk cosine, or None)
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
        similarities = [d["_vector_sim"] for _, d in scored if d.get("_vector_sim") is not None]
        results.append({
            "page_id": page_id,
            "id": unwrap_solr_value(best["id"], "id"),
            "url": unwrap_solr_value(best.get("url", ""), "url"),
            "title": unwrap_solr_value(best.get("title", ""), "title"),
            "domain": unwrap_solr_value(best.get("domain", ""), "domain"),
            "timestamp": unwrap_solr_value(best.get("timestamp", ""), "timestamp"),
            "text": unwrap_solr_value(best.get("text", ""), "text") or "",
            "description": unwrap_solr_value(best.get("description", ""), "description") or "",
            "fused_score": best_score + second_chunk_weight * second_score,
            "bm25_rank": best.get("_bm25_rank"),
            "knn_rank": best.get("_knn_rank"),
            "bm25_match": any(d.get("_bm25_rank") for _, d in scored),
            "vector_similarity": max(similarities) if similarities else None,
        })

    results.sort(key=lambda x: x["fused_score"], reverse=True)
    return results


def apply_relevance_floor(pages: list[dict], min_similarity: float = None) -> list[dict]:
    """Drop pages that matched no BM25 term and whose best chunk is less similar
    to the query than min_similarity (cosine)."""
    if min_similarity is None:
        min_similarity = MIN_VECTOR_SIMILARITY
    return [
        page for page in pages
        if page.get("bm25_match")
        or (page.get("vector_similarity") is not None and page["vector_similarity"] >= min_similarity)
    ]


@lru_cache(maxsize=1024)
def _cached_query_embedding(query: str) -> tuple[float, ...]:
    return tuple(embed_query(query))


def _page_filter_kwargs(page_ids):
    return {} if page_ids is None else {"page_ids": page_ids}


def _timed_bm25(solr, query: str, user_id: str, rows: int, page_ids=None):
    start = time.perf_counter()
    docs = solr.bm25_search(query, user_id, rows=rows, **_page_filter_kwargs(page_ids))
    return docs, (time.perf_counter() - start) * 1000


def _timed_knn(solr, query: str, user_id: str, k: int, page_ids=None):
    start = time.perf_counter()
    vector = list(_cached_query_embedding(query))
    embedded = time.perf_counter()
    docs = solr.knn_search(vector, user_id, k=k, **_page_filter_kwargs(page_ids))
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


def hybrid_search(query: str, user_id: str, top_k: int = None, candidate_pool: int = None,
                  timings: dict | None = None, solr: SolrClient | None = None,
                  page_ids: list[str] | None = None) -> list[dict]:
    """Full hybrid search pipeline.

    Steps:
    1. BM25 search and (embed query -> KNN search), concurrently
    2. Reciprocal Rank Fusion of the two ranked chunk lists
    3. Group by webpage (best chunk + weighted second-best chunk)
    4. Optionally rerank the top chunks with a cross-encoder (RERANK_ENABLED)
    5. Drop weak vector-only pages (MIN_VECTOR_SIMILARITY)
    6. Return top-K with snippets

    Only `user_id`'s chunks are searched. If `timings` is given, it is filled
    with per-stage durations in ms. `solr` targets a specific core. `page_ids`
    limits both searches to those pages (e.g. one map topic).
    Returns list of webpage-level results.
    """
    top_k = top_k or DEFAULT_TOP_K
    candidate_pool = candidate_pool or DEFAULT_CANDIDATE_POOL
    total_start = time.perf_counter()

    solr = solr or get_solr_client()

    bm25_future = _executor.submit(_timed_bm25, solr, query, user_id, candidate_pool, page_ids)
    knn_future = _executor.submit(_timed_knn, solr, query, user_id, candidate_pool, page_ids)
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
        similarity = knn_score_to_cosine(doc.get("score", 0.0))
        if doc["id"] in candidates_map:
            candidates_map[doc["id"]]["_knn_rank"] = rank
            candidates_map[doc["id"]]["_vector_sim"] = similarity
        else:
            doc["_bm25_rank"] = None
            doc["_knn_rank"] = rank
            doc["_vector_sim"] = similarity
            candidates_map[doc["id"]] = doc

    fused = rrf_fuse(
        [doc["id"] for doc in bm25_docs],
        [doc["id"] for doc in knn_docs],
        k=RRF_K, w_bm25=BM25_WEIGHT, w_knn=VECTOR_WEIGHT,
    )

    grouped = apply_relevance_floor(group_by_webpage(list(candidates_map.values()), fused))
    fuse_ms = (time.perf_counter() - fuse_start) * 1000

    rerank_ms = 0.0
    if RERANK_ENABLED and candidates_map:
        rerank_start = time.perf_counter()
        grouped = apply_relevance_floor(_rerank(query, candidates_map, fused, grouped))
        rerank_ms = (time.perf_counter() - rerank_start) * 1000

    results = grouped[:top_k]

    snippet_start = time.perf_counter()
    snippets = build_snippets(
        [(r.get("text", ""), r.get("description")) for r in results],
        query,
        query_vector=_cached_query_embedding(query),
        embed=_sentence_embeddings,
    )
    snippet_ms = (time.perf_counter() - snippet_start) * 1000
    for i, (result, snippet) in enumerate(zip(results, snippets)):
        result["rank"] = i + 1
        result["snippet"] = snippet

    stage_timings = {
        "embed_ms": round(embed_ms, 1),
        "bm25_ms": round(bm25_ms, 1),
        "knn_ms": round(knn_ms, 1),
        "fuse_ms": round(fuse_ms, 1),
        "rerank_ms": round(rerank_ms, 1),
        "snippet_ms": round(snippet_ms, 1),
        "total_ms": round((time.perf_counter() - total_start) * 1000, 1),
    }
    logger.info("Search timings: " + " ".join(f"{k}={v}" for k, v in stage_timings.items()))
    if timings is not None:
        timings.update(stage_timings)

    logger.info(f"Returning {len(results)} results")
    return results
