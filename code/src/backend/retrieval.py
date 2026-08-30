import logging
from backend.config import BM25_WEIGHT, VECTOR_WEIGHT, DEFAULT_CANDIDATE_POOL, DEFAULT_TOP_K
from backend.embeddings import get_embedding
from backend.solr_client import get_solr_client, unwrap_solr_value

logger = logging.getLogger(__name__)


def normalize_scores(docs_with_scores: list[tuple[str, float]]) -> dict[str, float]:
    """Min-max normalize scores to [0, 1].
    
    Handles edge cases:
    - Empty list: returns empty dict
    - Single result: returns score 1.0
    - Identical scores: returns 1.0 for all
    - Zero max: returns 0.0 for all
    """
    if not docs_with_scores:
        return {}
    
    scores = [s for _, s in docs_with_scores]
    min_score = min(scores)
    max_score = max(scores)
    
    if max_score == min_score:
        # All identical or single result -> normalize to 1.0
        return {doc_id: 1.0 for doc_id, _ in docs_with_scores}
    
    return {
        doc_id: (score - min_score) / (max_score - min_score)
        for doc_id, score in docs_with_scores
    }


def fuse_scores(bm25_normalized: dict[str, float], vector_normalized: dict[str, float],
                bm25_weight: float = None, vector_weight: float = None) -> dict[str, float]:
    """Fuse BM25 and vector scores.
    
    Documents appearing in only one method get 0.0 for the missing score.
    Result is guaranteed to have no NaN or infinity.
    """
    bm25_w = bm25_weight if bm25_weight is not None else BM25_WEIGHT
    vector_w = vector_weight if vector_weight is not None else VECTOR_WEIGHT
    
    all_ids = set(bm25_normalized.keys()) | set(vector_normalized.keys())
    
    fused = {}
    for doc_id in all_ids:
        bm25_score = bm25_normalized.get(doc_id, 0.0)
        vec_score = vector_normalized.get(doc_id, 0.0)
        fused[doc_id] = bm25_w * bm25_score + vector_w * vec_score
    
    return fused


def group_by_webpage(candidates: list[dict], fused_scores: dict[str, float]) -> list[dict]:
    """Group chunks by webpage_id. Highest-scoring chunk determines webpage rank.
    
    Returns list of webpage-level results with:
    - webpage_id, url, title, domain, timestamp
    - fused_score (from best chunk)
    - bm25_score, vector_score (from best chunk)
    """
    webpage_map = {}  # webpage_id -> best result dict
    
    for doc in candidates:
        doc_id = unwrap_solr_value(doc["id"], "id")
        webpage_id = unwrap_solr_value(doc.get("webpage_id", ""), "webpage_id")
        score = fused_scores.get(doc["id"], fused_scores.get(doc_id, 0.0))
        
        if webpage_id not in webpage_map or score > webpage_map[webpage_id]["fused_score"]:
            webpage_map[webpage_id] = {
                "webpage_id": webpage_id,
                "id": unwrap_solr_value(doc_id, "id"),
                "url": unwrap_solr_value(doc.get("url", ""), "url"),
                "title": unwrap_solr_value(doc.get("title", ""), "title"),
                "domain": unwrap_solr_value(doc.get("domain", ""), "domain"),
                "timestamp": unwrap_solr_value(doc.get("timestamp", ""), "timestamp"),
                "fused_score": score,
                "bm25_score": doc.get("_bm25_norm", 0.0),
                "vector_score": doc.get("_vector_norm", 0.0),
            }
    
    # Sort by fused_score descending
    results = sorted(webpage_map.values(), key=lambda x: x["fused_score"], reverse=True)
    return results


def hybrid_search(query: str, top_k: int = None, candidate_pool: int = None) -> list[dict]:
    """Full hybrid search pipeline.
    
    Steps:
    1. BM25 search
    2. Generate query embedding
    3. KNN search
    4. Normalize BM25 scores
    5. Normalize vector scores
    6. Fuse scores
    7. Group by webpage
    8. Return top-K
    
    Returns list of webpage-level results.
    """
    top_k = top_k or DEFAULT_TOP_K
    candidate_pool = candidate_pool or DEFAULT_CANDIDATE_POOL
    
    solr = get_solr_client()
    
    # Step 1: BM25 search
    logger.info(f"Running BM25 search for: {query}")
    bm25_docs = solr.bm25_search(query, rows=candidate_pool)
    logger.info(f"BM25 returned {len(bm25_docs)} candidates")
    
    # Step 2: Generate query embedding
    logger.info("Generating query embedding")
    query_embedding = get_embedding(query)
    
    # Step 3: KNN search
    logger.info(f"Running KNN search with k={candidate_pool}")
    knn_docs = solr.knn_search(query_embedding, k=candidate_pool)
    logger.info(f"KNN returned {len(knn_docs)} candidates")
    
    # Build candidate map (dedup by id)
    candidates_map = {}
    for doc in bm25_docs:
        candidates_map[doc["id"]] = doc
    for doc in knn_docs:
        if doc["id"] not in candidates_map:
            candidates_map[doc["id"]] = doc
    
    # Step 4: Normalize BM25 scores
    bm25_scores = [(doc["id"], doc.get("score", 0.0)) for doc in bm25_docs]
    bm25_normalized = normalize_scores(bm25_scores)
    
    # Step 5: Normalize vector scores
    vector_scores = [(doc["id"], doc.get("score", 0.0)) for doc in knn_docs]
    vector_normalized = normalize_scores(vector_scores)
    
    # Step 6: Fuse scores
    fused = fuse_scores(bm25_normalized, vector_normalized)
    logger.info(f"Fusion complete. Total candidates: {len(fused)}")
    
    # Annotate candidates with normalized scores for grouping
    for doc_id, doc in candidates_map.items():
        doc["_bm25_norm"] = bm25_normalized.get(doc_id, 0.0)
        doc["_vector_norm"] = vector_normalized.get(doc_id, 0.0)
    
    # Step 7: Group by webpage
    grouped = group_by_webpage(list(candidates_map.values()), fused)
    
    # Step 8: Return top-K
    results = grouped[:top_k]
    
    # Add rank
    for i, result in enumerate(results):
        result["rank"] = i + 1
    
    logger.info(f"Returning {len(results)} results")
    return results
