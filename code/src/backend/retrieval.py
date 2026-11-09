import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache

from backend.config import (
    BM25_WEIGHT, VECTOR_WEIGHT, DEFAULT_CANDIDATE_POOL, DEFAULT_TOP_K,
    RRF_K, PAGE_SECOND_CHUNK_WEIGHT, RERANK_ENABLED, RERANK_TOP_N, MIN_VECTOR_SIMILARITY,
    QUERY_INTENT_ENABLED, INTENT_WEIGHT, KEYWORD_FULL_MATCH,
)
from backend.embeddings import embed_passages, embed_query
from backend import rerank
from backend.query_intent import QueryIntent, parse_query
from backend.snippets import (  # noqa: F401
    SentenceEmbeddingCache, build_snippet, build_snippets, query_terms, term_score,
)
from backend.solr_client import (
    SolrClient, domains_filter, get_solr_client, page_ids_filter, saved_between_filter,
    unwrap_solr_value,
)
from backend.url_utils import generate_page_id

logger = logging.getLogger(__name__)

# Shared pool so BM25, (embed -> KNN) and the site/time BM25 run concurrently without paying
# thread start-up cost on every request.
_executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="retrieval")

# Embeddings of candidate snippet sentences (for picking the best sentence).
_sentence_embeddings = SentenceEmbeddingCache(lambda texts: embed_passages(texts))


def knn_score_to_cosine(score: float) -> float:
    """Solr's cosine DenseVectorField scores (1 + cos) / 2; undo that."""
    return 2.0 * float(score) - 1.0

def rrf_fuse_lists(ranked_lists: list[tuple[list[str], float]], k: int) -> dict[str, float]:
    """Reciprocal Rank Fusion of any number of (ranked ids, weight) lists.

    score(chunk) = sum over lists of weight / (k + rank), ranks start at 1.
    A chunk missing from a list gets nothing from it.
    """
    fused: dict[str, float] = {}
    for ids, weight in ranked_lists:
        for rank, doc_id in enumerate(ids, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + weight / (k + rank)
    return fused


def rrf_fuse(bm25_ids: list[str], knn_ids: list[str], k: int,
             w_bm25: float, w_knn: float) -> dict[str, float]:
    """Reciprocal Rank Fusion of the BM25 and KNN lists."""
    return rrf_fuse_lists([(bm25_ids, w_bm25), (knn_ids, w_knn)], k)


# ---- sites in the user's library (for site words in queries) ----------------

SITE_CACHE_SECONDS = 300
SITE_CACHE_USERS = 1000
_site_cache: dict[tuple[str, str], tuple[float, list[str]]] = {}
_site_lock = threading.Lock()


def user_domains(solr: SolrClient, user_id: str) -> list[str]:
    """The domains the user has saved pages from, cached for a few minutes
    (and dropped on save and delete, see forget_user_sites)."""
    key = (solr.base_url, user_id)
    now = time.monotonic()
    with _site_lock:
        cached = _site_cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
    domains = [domain for domain, _ in solr.list_domains(user_id)]
    with _site_lock:
        if len(_site_cache) >= SITE_CACHE_USERS:
            for old in sorted(_site_cache, key=lambda k: _site_cache[k][0])[: SITE_CACHE_USERS // 10]:
                _site_cache.pop(old, None)
        _site_cache[key] = (now + SITE_CACHE_SECONDS, domains)
    return domains


def forget_user_sites(user_id: str) -> None:
    with _site_lock:
        for key in [k for k in _site_cache if k[1] == user_id]:
            _site_cache.pop(key, None)


def _solr_date(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def intent_filters(intent: QueryIntent) -> list[str]:
    """Solr filters for the pages a query's site words or time phrase point at."""
    filters = []
    if intent.domains:
        filters.append(domains_filter(intent.domains))
    if intent.saved_from:
        filters.append(saved_between_filter(_solr_date(intent.saved_from), _solr_date(intent.saved_until)))
    return filters


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
            "intent_match": any(d.get("_intent_match") for _, d in scored),
            "vector_similarity": max(similarities) if similarities else None,
        })

    results.sort(key=lambda x: x["fused_score"], reverse=True)
    return results


def keyword_coverage(page: dict, terms: list[str]) -> float:
    """Share of the query's terms (snippets.query_terms) found in the page's
    title or best chunk, by prefix match. 1.0 for a query with no such terms."""
    if not terms:
        return 1.0
    text = f"{page.get('title') or ''} {page.get('text') or ''}"
    return term_score(text, terms) / len(terms)


def _strong_keyword_match(page: dict, terms: list[str] | None) -> bool:
    return terms is None or keyword_coverage(page, terms) >= KEYWORD_FULL_MATCH


def apply_relevance_floor(pages: list[dict], min_similarity: float = None,
                          terms: list[str] | None = None,
                          keyword_min_similarity: float = None) -> list[dict]:
    """Drop pages that aren't about the query.

    - Pages the query points at by site, time or URL (and that matched the rest
      of it by keyword, or there was no rest) are kept.
    - Pages that matched no BM25 term need a chunk at least `min_similarity`
      (cosine) to the query.
    - Pages that matched BM25 are kept when they hold most of the query's
      `terms` (KEYWORD_FULL_MATCH; so exact names and codes are never lost);
      a page that shares only some words ("greatest" and "time" for "greatest
      football player of all time") also needs `keyword_min_similarity`
      (default: `min_similarity`).
      Without `terms`, every BM25 match is kept.
    """
    if min_similarity is None:
        min_similarity = MIN_VECTOR_SIMILARITY
    if keyword_min_similarity is None:
        keyword_min_similarity = min_similarity

    def similar(page, threshold):
        return page.get("vector_similarity") is not None and page["vector_similarity"] >= threshold

    kept = []
    for page in pages:
        if page.get("intent_match"):
            kept.append(page)
        elif page.get("bm25_match"):
            if _strong_keyword_match(page, terms) or similar(page, keyword_min_similarity):
                kept.append(page)
        elif similar(page, min_similarity):
            kept.append(page)
    return kept


# Pages whose similarity is looked up after fusion, and chunks fetched for them.
SIMILARITY_CHECK_MAX_PAGES = 50
SIMILARITY_CHECK_CHUNKS_PER_PAGE = 8
SIMILARITY_CHECK_MAX_CHUNKS = 300


def fill_keyword_similarity(solr: SolrClient, pages: list[dict], terms: list[str], user_id: str,
                            query_vector, page_ids=None) -> int:
    """Give partial keyword matches with no vector similarity one: a KNN over
    just those pages' chunks (one Solr request). Their chunks weren't in the
    main KNN list, so without this the floor couldn't judge them.
    Returns how many pages were looked up."""
    need = [
        page for page in pages
        if page.get("bm25_match") and not page.get("intent_match")
        and page.get("vector_similarity") is None and not _strong_keyword_match(page, terms)
    ][:SIMILARITY_CHECK_MAX_PAGES]
    if not need:
        return 0
    ids = [page["page_id"] for page in need]
    if page_ids is not None:
        allowed = set(page_ids)
        ids = [i for i in ids if i in allowed]
        if not ids:
            return 0
    k = min(SIMILARITY_CHECK_CHUNKS_PER_PAGE * len(ids), SIMILARITY_CHECK_MAX_CHUNKS)
    docs = solr.knn_search(list(query_vector()), user_id, k=k, page_ids=ids)
    best: dict[str, float] = {}
    for doc in docs:
        page_id = unwrap_solr_value(doc.get("page_id", ""), "page_id")
        similarity = knn_score_to_cosine(doc.get("score", 0.0))
        best[page_id] = max(similarity, best.get(page_id, -1.0))
    for page in need:
        if page["page_id"] in best:
            page["vector_similarity"] = best[page["page_id"]]
    return len(ids)


@lru_cache(maxsize=1024)
def _cached_query_embedding(query: str) -> tuple[float, ...]:
    return tuple(embed_query(query))


def _page_filter_kwargs(page_ids):
    return {} if page_ids is None else {"page_ids": page_ids}


def _timed_bm25(solr, query: str, user_id: str, rows: int, page_ids=None, filters=None):
    start = time.perf_counter()
    kwargs = _page_filter_kwargs(page_ids)
    if filters:
        kwargs["filters"] = filters
    docs = solr.bm25_search(query, user_id, rows=rows, **kwargs)
    return docs, (time.perf_counter() - start) * 1000


def _timed_knn(solr, query: str, user_id: str, k: int, page_ids=None, filters=None):
    start = time.perf_counter()
    vector = list(_cached_query_embedding(query))
    embedded = time.perf_counter()
    kwargs = _page_filter_kwargs(page_ids)
    if filters:
        kwargs["filters"] = filters
    docs = solr.knn_search(vector, user_id, k=k, **kwargs)
    done = time.perf_counter()
    return docs, (embedded - start) * 1000, (done - embedded) * 1000


def _intent_lists(solr, intent: QueryIntent, user_id: str, rows: int, page_ids,
                  query_vector) -> list[tuple[list[dict], float, str]]:
    """Ranked lists of just the pages the query points at, as (docs, weight, kind).

    With words left over, BM25 for them and KNN for the whole query (reusing its
    vector, so no second embedding) within those pages; with none ("my reddit
    saves", "what I read yesterday"), those pages nearest the named day or newest
    first. A URL query also puts that saved page first. `query_vector()` waits for
    the main search's embedding.
    """
    lists = []
    filters = intent_filters(intent)
    if filters:
        if intent.text:
            bm25 = _executor.submit(_timed_bm25, solr, intent.text, user_id, rows, page_ids, filters)
            knn = solr.knn_search(query_vector(), user_id, k=rows, filters=filters,
                                  **_page_filter_kwargs(page_ids))
            lists.append((bm25.result()[0], BM25_WEIGHT * INTENT_WEIGHT, "bm25"))
            lists.append((knn, VECTOR_WEIGHT * INTENT_WEIGHT, "knn"))
        else:
            if page_ids is not None:
                filters = filters + [page_ids_filter(page_ids)]
            near = _solr_date(intent.saved_near) if intent.saved_near else None
            # The query is only where or when, so the main lists have little to go on:
            # this list counts as much as both of them together, twice over.
            lists.append((solr.recent_pages(user_id, filters, rows=rows, near=near),
                          2 * (BM25_WEIGHT + VECTOR_WEIGHT) * INTENT_WEIGHT, "recent"))
    if intent.url:
        head = solr.get_page_head(generate_page_id(user_id, intent.url), user_id)
        if head and (page_ids is None or head.get("page_id") in page_ids):
            # Far ahead of anything else: the person typed this page's address.
            lists.append(([head], 10 * (BM25_WEIGHT + VECTOR_WEIGHT), "url"))
    return lists


def _query_intent(solr, query: str, user_id: str) -> QueryIntent | None:
    if not QUERY_INTENT_ENABLED:
        return None
    try:
        return parse_query(query, user_domains(solr, user_id))
    except Exception as e:  # never let this break a search
        logger.warning(f"Query intent skipped: {e}")
        return None


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
                  page_ids: list[str] | None = None, snippets: bool = True) -> list[dict]:
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
    limits both searches to those pages (e.g. one map topic). `snippets=False`
    skips snippets for callers that only need the ranking.
    Returns list of webpage-level results.
    """
    top_k = top_k or DEFAULT_TOP_K
    candidate_pool = candidate_pool or DEFAULT_CANDIDATE_POOL
    total_start = time.perf_counter()

    solr = solr or get_solr_client()

    bm25_future = _executor.submit(_timed_bm25, solr, query, user_id, candidate_pool, page_ids)
    knn_future = _executor.submit(_timed_knn, solr, query, user_id, candidate_pool, page_ids)

    # Meanwhile: does the query name a site, a time or a URL?
    intent_start = time.perf_counter()
    intent = _query_intent(solr, query, user_id)
    intent_lists = []
    if intent and intent.active:
        try:
            def query_vector():
                knn_future.result()  # it embeds the query first; the vector is then cached
                return list(_cached_query_embedding(query))

            intent_lists = _intent_lists(solr, intent, user_id, candidate_pool, page_ids, query_vector)
        except Exception as e:
            logger.warning(f"Query intent search skipped: {e}")
    intent_ms = (time.perf_counter() - intent_start) * 1000

    bm25_docs, bm25_ms = bm25_future.result()
    knn_docs, embed_ms, knn_ms = knn_future.result()
    logger.info(f"BM25 returned {len(bm25_docs)} candidates, KNN returned {len(knn_docs)}"
                + (f", intent lists {[len(docs) for docs, _, _ in intent_lists]}" if intent_lists else ""))

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

    for docs, _, kind in intent_lists:
        for doc in docs:
            current = candidates_map.get(doc["id"])
            if current is None:
                doc.setdefault("_bm25_rank", None)
                doc.setdefault("_knn_rank", None)
                candidates_map[doc["id"]] = current = doc
            if kind == "knn":
                similarity = knn_score_to_cosine(doc.get("score", 0.0))
                current["_vector_sim"] = max(similarity, current.get("_vector_sim") or -1.0)
            else:
                current["_intent_match"] = True

    fused = rrf_fuse_lists(
        [([doc["id"] for doc in bm25_docs], BM25_WEIGHT), ([doc["id"] for doc in knn_docs], VECTOR_WEIGHT)]
        + [([doc["id"] for doc in docs], weight) for docs, weight, _ in intent_lists],
        k=RRF_K,
    )

    terms = query_terms(query)
    all_pages = group_by_webpage(list(candidates_map.values()), fused)
    try:
        fill_keyword_similarity(solr, all_pages, terms, user_id,
                                lambda: _cached_query_embedding(query), page_ids)
    except Exception as e:  # never let this break a search; the floor then drops them
        logger.warning(f"Similarity check of keyword matches skipped: {e}")
    grouped = apply_relevance_floor(all_pages, terms=terms)
    fuse_ms = (time.perf_counter() - fuse_start) * 1000

    rerank_ms = 0.0
    if RERANK_ENABLED and candidates_map:
        rerank_start = time.perf_counter()
        reranked = _rerank(query, candidates_map, fused, grouped)
        # Reranking regroups pages from their chunks: keep the similarities looked up above.
        looked_up = {p["page_id"]: p.get("vector_similarity") for p in all_pages}
        for page in reranked:
            if page.get("vector_similarity") is None:
                page["vector_similarity"] = looked_up.get(page["page_id"])
        grouped = apply_relevance_floor(reranked, terms=terms)
        rerank_ms = (time.perf_counter() - rerank_start) * 1000

    results = grouped[:top_k]

    snippet_start = time.perf_counter()
    texts = build_snippets(
        [(r.get("text", ""), r.get("description")) for r in results],
        query,
        query_vector=_cached_query_embedding(query),
        embed=_sentence_embeddings,
    ) if snippets else [None] * len(results)
    snippet_ms = (time.perf_counter() - snippet_start) * 1000
    for i, (result, snippet) in enumerate(zip(results, texts)):
        result["rank"] = i + 1
        result["snippet"] = snippet

    stage_timings = {
        "embed_ms": round(embed_ms, 1),
        "bm25_ms": round(bm25_ms, 1),
        "knn_ms": round(knn_ms, 1),
        "intent_ms": round(intent_ms, 1),
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
