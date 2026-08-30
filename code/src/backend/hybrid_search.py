# hybrid_search.py
#
# BM25 + dense (ChromaDB/MiniLM) hybrid retrieval, kept in its own module so
# that both the FastAPI backend (main.py) and the evaluation script
# (evaluate_hybrid.py) exercise the exact same retrieval code — no drift
# between what gets evaluated and what actually runs.
#
# Design decisions (see the accompanying write-up for full reasoning):
#   - BM25 indexes title + content only, not URL (URLs are lexically noisy).
#   - Title tokens are repeated 3x ahead of body tokens as a simple field
#     boost, instead of maintaining a second title-only BM25 index.
#   - The BM25 index is rebuilt from ChromaDB on startup rather than
#     persisted separately — ChromaDB is already the durable source of
#     truth, so a second serialized index would just be a second thing that
#     can drift out of sync with it.
#   - Fusion is Reciprocal Rank Fusion (RRF), not a normalized weighted sum
#     — RRF only depends on rank position, so it needs no score calibration
#     between BM25's unbounded scores and ChromaDB's cosine similarity.

import re
from typing import Dict, List, Optional, Tuple

from rank_bm25 import BM25Okapi

# ── Tokenization ─────────────────────────────────────────────────────────
# Treats . + # _ - as token-internal characters so "React.js", "C++",
# "useEffect", "gpt-4", "PostgreSQL" survive as single tokens instead of
# being shredded on punctuation. A single trailing "." is stripped
# afterward (sentence-ending periods), since that's the one case this
# pattern can't distinguish from a genuine abbreviation/version token.
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[.+#_-]+[A-Za-z0-9]*)*")
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Field boosting: title tokens are repeated this many times ahead of the
# body, approximating "title matches matter more" without a second index.
TITLE_BOOST_REPEAT = 3

# Safety ceiling on how many tokens of a single document BM25 will index.
# Not a normal-case limit — most extracted articles are far shorter — just
# a guard against one pathological page ballooning index build time.
MAX_DOC_TOKENS = 8000

# How many candidates each retriever contributes before fusion. rank_bm25
# scores the whole corpus per query (no approximate indexing), so this is
# "score everything, keep the top N" rather than a true limited retrieval —
# fine at personal-browsing-history scale; revisit if the corpus grows into
# the tens of thousands of pages (see the Solr discussion elsewhere).
DEFAULT_CANDIDATE_POOL = 30

# RRF's own hyperparameter — how sharply top ranks are favored over lower
# ones. Swept explicitly in evaluate_hybrid.py rather than assumed.
DEFAULT_RRF_K = 60


def tokenize(text: str) -> List[str]:
    """Lowercase, strip stray HTML, and extract tokens that keep technical
    terms like 'C++', 'React.js', 'useEffect' intact. No stopword removal —
    BM25's own IDF term already downweights ubiquitous words."""
    if not text:
        return []
    text = _HTML_TAG_RE.sub(" ", text.lower())
    tokens = []
    for tok in _TOKEN_RE.findall(text):
        if tok.endswith("."):
            tok = tok[:-1]
        if tok:
            tokens.append(tok)
    return tokens[:MAX_DOC_TOKENS]


def build_bm25_document(title: str, content: str) -> List[str]:
    """One memory's token list: title tokens repeated for emphasis, then
    body tokens once. This is what actually gets indexed by BM25Okapi."""
    title_tokens = tokenize(title or "")
    body_tokens = tokenize(content or "")
    return (title_tokens * TITLE_BOOST_REPEAT) + body_tokens


# ── BM25 index ───────────────────────────────────────────────────────────

class BM25Index:
    """In-memory BM25 index over stored memories, keyed by the same memory
    id ChromaDB uses (the sanitized URL). Rebuilt from ChromaDB at startup;
    updated in place on every /memory upsert so it never needs its own
    persistence file."""

    def __init__(self):
        self.ids: List[str] = []
        self.tokenized_docs: List[List[str]] = []
        self.metadata: Dict[str, dict] = {}  # id -> {"title": ..., "url": ...}
        self._bm25: Optional[BM25Okapi] = None
        self._id_to_pos: Dict[str, int] = {}

    def _rebuild_bm25(self):
        # rank_bm25 has no incremental-update API — every insert/update
        # rebuilds the whole model. Cheap at this corpus scale (see module
        # docstring); would need a different approach at much larger scale.
        if self.tokenized_docs:
            self._bm25 = BM25Okapi(self.tokenized_docs)
        else:
            self._bm25 = None

    def build_from_chromadb(self, collection) -> int:
        """Full rebuild from whatever ChromaDB already has stored. This is
        what runs once at server startup."""
        self.ids = []
        self.tokenized_docs = []
        self.metadata = {}
        self._id_to_pos = {}

        count = collection.count()
        if count == 0:
            self._bm25 = None
            return 0

        data = collection.get(include=["metadatas", "documents"])
        for memory_id, metadata, document in zip(
            data["ids"], data["metadatas"], data["documents"]
        ):
            title = (metadata or {}).get("title", "")
            url = (metadata or {}).get("url", "")
            tokens = build_bm25_document(title, document or "")
            self._id_to_pos[memory_id] = len(self.ids)
            self.ids.append(memory_id)
            self.tokenized_docs.append(tokens)
            self.metadata[memory_id] = {"title": title, "url": url}

        self._rebuild_bm25()
        return len(self.ids)

    def upsert(self, memory_id: str, title: str, content: str):
        """Called right after collection.upsert() in /memory. Matches
        ChromaDB's upsert semantics: same id updates in place, new id
        appends — no duplicate BM25 documents for the same memory."""
        tokens = build_bm25_document(title, content)
        self.metadata[memory_id] = {"title": title, "url": None}  # url set by caller if needed

        if memory_id in self._id_to_pos:
            pos = self._id_to_pos[memory_id]
            self.tokenized_docs[pos] = tokens
        else:
            self._id_to_pos[memory_id] = len(self.ids)
            self.ids.append(memory_id)
            self.tokenized_docs.append(tokens)

        self._rebuild_bm25()

    def search(self, query_text: str, top_k: int = DEFAULT_CANDIDATE_POOL) -> List[Tuple[str, float]]:
        """Returns [(memory_id, bm25_score), ...] sorted best-first."""
        if self._bm25 is None or not self.ids:
            return []
        query_tokens = tokenize(query_text)
        if not query_tokens:
            return []
        scores = self._bm25.get_scores(query_tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        results = []
        for i in ranked[:top_k]:
            if scores[i] > 0:  # drop zero-overlap documents entirely
                results.append((self.ids[i], float(scores[i])))
        return results


# ── Fusion ───────────────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    ranked_lists: List[List[str]], k: int = DEFAULT_RRF_K
) -> List[Tuple[str, float]]:
    """Standard RRF over any number of ranked id lists (best-first).
    RRF(d) = sum over lists containing d of 1 / (k + rank_in_that_list).
    A document missing from a list simply contributes 0 for that list —
    it isn't penalized beyond just not getting that list's points."""
    scores: Dict[str, float] = {}
    for ranked_ids in ranked_lists:
        for rank, doc_id in enumerate(ranked_ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def normalize_minmax(scored: List[Tuple[str, float]]) -> Dict[str, float]:
    """Min-max normalization, provided for completeness/debugging if you
    want to experiment with weighted-sum fusion instead of RRF — not used
    by the default hybrid path. See the write-up for why RRF was chosen
    instead of relying on this."""
    if not scored:
        return {}
    values = [v for _, v in scored]
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return {doc_id: 1.0 for doc_id, _ in scored}
    return {doc_id: (v - lo) / (hi - lo) for doc_id, v in scored}


# ── Orchestration ────────────────────────────────────────────────────────

def hybrid_search(
    collection,
    embedding_model,
    bm25_index: BM25Index,
    query_text: str,
    num_results: int = 5,
    mode: str = "hybrid",  # "hybrid" | "semantic" | "bm25"
    candidate_pool: int = DEFAULT_CANDIDATE_POOL,
    rrf_k: int = DEFAULT_RRF_K,
) -> List[dict]:
    """Runs retrieval per `mode` and returns a rank-ordered list of dicts:
    {id, bm25_score, semantic_score, hybrid_score}. Does NOT touch
    ChromaDB metadata/documents for display, and does NOT call Gemini —
    the caller (main.py) is responsible for both, keeping summarization
    strictly downstream of retrieval as required."""

    bm25_ranked_ids: List[str] = []
    bm25_scores: Dict[str, float] = {}
    semantic_ranked_ids: List[str] = []
    semantic_scores: Dict[str, float] = {}

    if mode in ("hybrid", "bm25"):
        try:
            bm25_results = bm25_index.search(query_text, top_k=candidate_pool)
            bm25_ranked_ids = [doc_id for doc_id, _ in bm25_results]
            bm25_scores = dict(bm25_results)
            print(f"[Hybrid Search] BM25 candidates: {len(bm25_ranked_ids)}")
        except Exception as e:
            # graceful fallback (requirement: don't fail the whole search
            # if BM25 breaks) — log and continue as if BM25 found nothing
            print(f"[Hybrid Search] ✗ BM25 failed, falling back to semantic-only: {e}")
            bm25_ranked_ids, bm25_scores = [], {}

    if mode in ("hybrid", "semantic"):
        count = collection.count()
        if count > 0:
            query_embedding = embedding_model.encode(
                query_text, convert_to_numpy=True
            ).tolist()
            raw = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(candidate_pool, count),
                include=["distances"],
            )
            for doc_id, distance in zip(raw["ids"][0], raw["distances"][0]):
                semantic_ranked_ids.append(doc_id)
                semantic_scores[doc_id] = max(0.0, 1 - distance)
            print(f"[Hybrid Search] Semantic candidates: {len(semantic_ranked_ids)}")

    if mode == "bm25":
        fused_ids = bm25_ranked_ids
        fused_scores = {doc_id: score for doc_id, score in bm25_scores.items()}
    elif mode == "semantic":
        fused_ids = semantic_ranked_ids
        fused_scores = {doc_id: score for doc_id, score in semantic_scores.items()}
    else:  # hybrid
        fused = reciprocal_rank_fusion([bm25_ranked_ids, semantic_ranked_ids], k=rrf_k)
        fused_ids = [doc_id for doc_id, _ in fused]
        fused_scores = dict(fused)

    unique_candidates = set(bm25_ranked_ids) | set(semantic_ranked_ids)
    print(f"[Hybrid Search] Unique candidates: {len(unique_candidates)}")
    print(f"[Hybrid Search] Returning: {min(num_results, len(fused_ids))}")

    results = []
    for doc_id in fused_ids[:num_results]:
        results.append({
            "id": doc_id,
            "bm25_score": bm25_scores.get(doc_id),
            "semantic_score": semantic_scores.get(doc_id),
            "hybrid_score": fused_scores.get(doc_id),
        })
    return results
