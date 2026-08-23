import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any
from urllib.parse import urlsplit, urlunsplit

import chromadb
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

CHROMA_DB_PATH = "./chroma_db"
EVAL_DATA_PATH = "./evaluation.json"
OUTPUT_PATH = "./evaluation_report.json"

COLLECTION_NAME = "memorylane_chunks"

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"

# Number of candidates retrieved from each first-stage retriever.
CANDIDATE_K = 50

# Hybrid fusion weights.
SEMANTIC_WEIGHT = 0.6
BM25_WEIGHT = 0.4

# Metrics to calculate.
METRIC_KS = [1, 3, 5, 10]


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)

logger = logging.getLogger("MemoryLaneEvaluation")


# ============================================================
# URL NORMALIZATION
# ============================================================

def normalize_url(url: str) -> str:
    """
    Normalize URLs for evaluation.

    Removes:
    - fragments
    - trailing slash differences

    Does NOT remove query parameters because they may identify
    genuinely different webpages.
    """
    if not url:
        return ""

    url = url.strip()

    try:
        parsed = urlsplit(url)

        # Remove fragment
        normalized = urlunsplit((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            parsed.query,
            ""
        ))

        return normalized

    except Exception:
        return url.rstrip("/").lower()


# ============================================================
# TOKENIZATION
# ============================================================

def tokenize(text: str) -> List[str]:
    """
    Simple tokenizer for BM25.
    """
    return re.findall(
        r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*",
        (text or "").lower()
    )


# ============================================================
# SCORE NORMALIZATION
# ============================================================

def min_max_normalize(values: List[float]) -> List[float]:
    """
    Normalize scores into [0, 1].

    Required because BM25 and semantic similarity are on
    completely different scales.
    """
    if not values:
        return []

    minimum = min(values)
    maximum = max(values)

    if maximum == minimum:
        return [1.0] * len(values)

    return [
        (value - minimum) / (maximum - minimum)
        for value in values
    ]


# ============================================================
# RETRIEVER
# ============================================================

class MemoryLaneRetriever:

    def __init__(self):
        logger.info("Initializing MemoryLane evaluation retriever...")

        logger.info(
            f"Loading embedding model: {EMBEDDING_MODEL_NAME}"
        )

        self.embedding_model = SentenceTransformer(
            EMBEDDING_MODEL_NAME
        )

        logger.info(
            f"Loading reranker: {RERANKER_MODEL_NAME}"
        )

        self.reranker = CrossEncoder(
            RERANKER_MODEL_NAME
        )

        logger.info("Connecting to ChromaDB...")

        client = chromadb.PersistentClient(
            path=CHROMA_DB_PATH
        )

        # Prefer the expected collection, but fall back to the
        # only available collection if its name differs.
        collections = client.list_collections()

        if not collections:
            raise RuntimeError(
                "No ChromaDB collections were found."
            )

        collection_names = [
            c.name if hasattr(c, "name") else str(c)
            for c in collections
        ]

        if COLLECTION_NAME in collection_names:
            selected_name = COLLECTION_NAME
        elif len(collection_names) == 1:
            selected_name = collection_names[0]
        else:
            raise RuntimeError(
                f"Collection '{COLLECTION_NAME}' not found.\n"
                f"Available collections: {collection_names}"
            )

        logger.info(
            f"Using ChromaDB collection: {selected_name}"
        )

        self.collection = client.get_collection(
            name=selected_name
        )

        count = self.collection.count()

        if count == 0:
            raise RuntimeError(
                "ChromaDB collection is empty."
            )

        logger.info(
            f"ChromaDB contains {count} chunks."
        )

        self._load_bm25_index()

    # --------------------------------------------------------
    # BM25 INDEX
    # --------------------------------------------------------

    def _load_bm25_index(self):
        logger.info("Loading all chunks for BM25...")

        data = self.collection.get(
            include=["documents", "metadatas"]
        )

        self.documents = data["documents"] or []
        self.metadatas = data["metadatas"] or []
        self.doc_ids = data["ids"] or []

        if not self.documents:
            raise RuntimeError(
                "No documents found in ChromaDB."
            )

        tokenized_documents = [
            tokenize(document)
            for document in self.documents
        ]

        self.bm25 = BM25Okapi(
            tokenized_documents
        )

        logger.info(
            f"BM25 index ready with {len(self.documents)} chunks."
        )

    # --------------------------------------------------------
    # CHROMA SEMANTIC SEARCH
    # --------------------------------------------------------

    def semantic_search(
        self,
        query: str,
        n_results: int = CANDIDATE_K
    ) -> List[Dict[str, Any]]:

        query_embedding = self.embedding_model.encode(
            query,
            convert_to_numpy=True
        ).tolist()

        n_results = min(
            n_results,
            self.collection.count()
        )

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=[
                "documents",
                "metadatas",
                "distances"
            ]
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        output = []

        for doc, metadata, distance in zip(
            documents,
            metadatas,
            distances
        ):
            # Chroma uses cosine distance here.
            similarity = 1.0 - float(distance)

            output.append({
                "doc": doc,
                "metadata": metadata or {},
                "semantic_score": similarity
            })

        return output

    # --------------------------------------------------------
    # BM25 SEARCH
    # --------------------------------------------------------

    def bm25_search(
        self,
        query: str,
        n_results: int = CANDIDATE_K
    ) -> List[Dict[str, Any]]:

        query_tokens = tokenize(query)

        if not query_tokens:
            return []

        scores = self.bm25.get_scores(
            query_tokens
        )

        ranked_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )

        output = []

        for idx in ranked_indices[:n_results]:
            score = float(scores[idx])

            if score <= 0:
                continue

            output.append({
                "index": idx,
                "doc": self.documents[idx],
                "metadata": self.metadatas[idx] or {},
                "bm25_score": score
            })

        return output

    # --------------------------------------------------------
    # HYBRID SEARCH
    # --------------------------------------------------------

    def hybrid_search(
        self,
        query: str
    ) -> List[Dict[str, Any]]:
        """
        Run semantic + BM25 retrieval and fuse candidates.
        """

        semantic_results = self.semantic_search(
            query,
            CANDIDATE_K
        )

        bm25_results = self.bm25_search(
            query,
            CANDIDATE_K
        )

        logger.debug(
            f"Semantic candidates: {len(semantic_results)}"
        )

        logger.debug(
            f"BM25 candidates: {len(bm25_results)}"
        )

        # Use stable chunk IDs where possible.
        # Falling back to text is safer than accidentally
        # collapsing chunks from different URLs with identical text.
        combined = {}

        # ----------------------------------------------------
        # Semantic candidates
        # ----------------------------------------------------

        semantic_scores = [
            item["semantic_score"]
            for item in semantic_results
        ]

        normalized_semantic = min_max_normalize(
            semantic_scores
        )

        for item, normalized_score in zip(
            semantic_results,
            normalized_semantic
        ):
            key = self._candidate_key(
                item["metadata"],
                item["doc"]
            )

            combined[key] = {
                "doc": item["doc"],
                "metadata": item["metadata"],
                "semantic_score": normalized_score,
                "bm25_score": 0.0
            }

        # ----------------------------------------------------
        # BM25 candidates
        # ----------------------------------------------------

        bm25_scores = [
            item["bm25_score"]
            for item in bm25_results
        ]

        normalized_bm25 = min_max_normalize(
            bm25_scores
        )

        for item, normalized_score in zip(
            bm25_results,
            normalized_bm25
        ):
            key = self._candidate_key(
                item["metadata"],
                item["doc"]
            )

            if key not in combined:
                combined[key] = {
                    "doc": item["doc"],
                    "metadata": item["metadata"],
                    "semantic_score": 0.0,
                    "bm25_score": normalized_score
                }
            else:
                combined[key]["bm25_score"] = max(
                    combined[key]["bm25_score"],
                    normalized_score
                )

        # ----------------------------------------------------
        # Weighted fusion
        # ----------------------------------------------------

        candidates = []

        for item in combined.values():

            hybrid_score = (
                SEMANTIC_WEIGHT
                * item["semantic_score"]
                +
                BM25_WEIGHT
                * item["bm25_score"]
            )

            candidates.append({
                "doc": item["doc"],
                "metadata": item["metadata"],
                "hybrid_score": hybrid_score
            })

        candidates.sort(
            key=lambda x: x["hybrid_score"],
            reverse=True
        )

        return candidates[:CANDIDATE_K]

    # --------------------------------------------------------
    # RERANKING
    # --------------------------------------------------------

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:

        if not candidates:
            return []

        pairs = [
            (
                query,
                candidate["doc"]
            )
            for candidate in candidates
        ]

        scores = self.reranker.predict(
            pairs,
            show_progress_bar=False
        )

        for candidate, score in zip(
            candidates,
            scores
        ):
            candidate["rerank_score"] = float(score)

        candidates.sort(
            key=lambda x: x["rerank_score"],
            reverse=True
        )

        return candidates

    # --------------------------------------------------------
    # ADAPTIVE CUTOFF
    # --------------------------------------------------------

    @staticmethod
    def adaptive_cutoff(
        reranked_chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Find the biggest score drop ("elbow") and retain
        results before that point.

        No fixed relevance threshold is used.
        """

        if len(reranked_chunks) <= 1:
            return reranked_chunks

        scores = [
            item["rerank_score"]
            for item in reranked_chunks
        ]

        # Largest consecutive score drop.
        gaps = [
            scores[i] - scores[i + 1]
            for i in range(len(scores) - 1)
        ]

        largest_gap_index = max(
            range(len(gaps)),
            key=lambda i: gaps[i]
        )

        cutoff_index = largest_gap_index + 1

        return reranked_chunks[:cutoff_index]

    # --------------------------------------------------------
    # GROUP CHUNKS -> WEBPAGES
    # --------------------------------------------------------

    @staticmethod
    def group_chunks_by_url(
        reranked_chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Since chunks are already sorted by reranker score,
        the first chunk encountered for a URL is automatically
        that webpage's highest-ranked chunk.

        Therefore webpage ordering is determined by the
        highest-ranked chunk, exactly as required.
        """

        pages = {}

        for chunk in reranked_chunks:

            raw_url = chunk["metadata"].get(
                "url",
                ""
            )

            if not raw_url:
                continue

            url = normalize_url(raw_url)

            if url not in pages:

                pages[url] = {
                    "url": raw_url,
                    "title": chunk["metadata"].get(
                        "title",
                        "Untitled"
                    ),
                    "best_score": chunk[
                        "rerank_score"
                    ],
                    "chunks": [chunk["doc"]]
                }

            else:
                pages[url]["chunks"].append(
                    chunk["doc"]
                )

        # Dictionary insertion order already corresponds
        # to highest-ranked first occurrence.
        return list(pages.values())

    # --------------------------------------------------------
    # COMPLETE RETRIEVAL PIPELINE
    # --------------------------------------------------------

    def retrieve(
        self,
        query: str
    ) -> Dict[str, Any]:
        """
        Complete evaluation retrieval pipeline:

        Query
          ↓
        Chroma semantic search
          +
        BM25 search
          ↓
        Hybrid fusion
          ↓
        Reranking
          ↓
        Unique webpage ranking
          ↓
        Adaptive cutoff
        """

        hybrid_candidates = self.hybrid_search(
            query
        )

        reranked_chunks = self.rerank(
            query,
            hybrid_candidates
        )

        # IMPORTANT:
        # First build the complete ranked URL list.
        # This allows Recall@K / MRR to measure the actual
        # reranking quality before adaptive display cutoff.
        ranked_pages_before_cutoff = (
            self.group_chunks_by_url(
                reranked_chunks
            )
        )

        # Production-style dynamic selection.
        cutoff_chunks = self.adaptive_cutoff(
            reranked_chunks
        )

        ranked_pages_after_cutoff = (
            self.group_chunks_by_url(
                cutoff_chunks
            )
        )

        return {
            "ranked_pages_before_cutoff":
                ranked_pages_before_cutoff,

            "ranked_pages_after_cutoff":
                ranked_pages_after_cutoff,

            "reranked_chunks":
                reranked_chunks,

            "cutoff_chunks":
                cutoff_chunks
        }

    # --------------------------------------------------------
    # CANDIDATE KEY
    # --------------------------------------------------------

    @staticmethod
    def _candidate_key(
        metadata: Dict[str, Any],
        document: str
    ) -> str:
        """
        Avoid collapsing two different chunks that happen
        to have identical text.
        """

        url = metadata.get("url", "")
        chunk_id = metadata.get("chunk_id", "")

        if url or chunk_id:
            return f"{url}::{chunk_id}"

        return document


# ============================================================
# METRICS
# ============================================================

def calculate_metrics(
    retriever: MemoryLaneRetriever,
    evaluation_data: List[Dict[str, Any]]
) -> Dict[str, Any]:

    total_queries = len(evaluation_data)

    if total_queries == 0:
        raise ValueError(
            "Evaluation dataset is empty."
        )

    # Hits for each K.
    hit_counts = {
        k: 0
        for k in METRIC_KS
    }

    precision_sums = {
        k: 0.0
        for k in METRIC_KS
    }

    reciprocal_ranks = []

    # Adaptive output statistics.
    adaptive_result_counts = []

    # Detailed failures are useful for debugging.
    failures = []

    for index, item in enumerate(
        evaluation_data,
        start=1
    ):

        query = item.get("query", "").strip()
        expected_url = normalize_url(
            item.get("expected_url", "")
        )

        if not query or not expected_url:
            continue

        logger.info(
            f"[{index}/{total_queries}] {query}"
        )

        try:
            retrieval = retriever.retrieve(
                query
            )

        except Exception as exc:
            logger.error(
                f"Retrieval failed: {exc}"
            )

            failures.append({
                "query": query,
                "expected_url": expected_url,
                "error": str(exc)
            })

            continue

        ranked_pages = (
            retrieval[
                "ranked_pages_before_cutoff"
            ]
        )

        adaptive_pages = (
            retrieval[
                "ranked_pages_after_cutoff"
            ]
        )

        ranked_urls = [
            normalize_url(
                page["url"]
            )
            for page in ranked_pages
        ]

        adaptive_urls = [
            normalize_url(
                page["url"]
            )
            for page in adaptive_pages
        ]

        adaptive_result_counts.append(
            len(adaptive_urls)
        )

        # ----------------------------------------------------
        # Find rank of correct webpage
        # ----------------------------------------------------

        try:
            rank = (
                ranked_urls.index(
                    expected_url
                ) + 1
            )

        except ValueError:
            rank = None

        # ----------------------------------------------------
        # Recall@K / Hit@K
        # ----------------------------------------------------

        for k in METRIC_KS:

            if expected_url in ranked_urls[:k]:

                hit_counts[k] += 1

                # Standard Precision@K:
                # one relevant webpage exists in this
                # evaluation case.
                precision_sums[k] += (
                    1.0 / k
                )

        # ----------------------------------------------------
        # MRR
        # ----------------------------------------------------

        if rank is not None:
            reciprocal_ranks.append(
                1.0 / rank
            )
        else:
            reciprocal_ranks.append(0.0)

            failures.append({
                "query": query,
                "expected_url": expected_url,
                "retrieved_top_10": ranked_urls[:10]
            })

    evaluated_queries = (
        total_queries - len(failures)
        + sum(
            1
            for f in failures
            if "retrieved_top_10" in f
        )
    )

    # We want denominator to represent all actual
    # evaluation cases. Invalid cases are excluded.
    valid_cases = [
        item for item in evaluation_data
        if item.get("query", "").strip()
        and item.get("expected_url", "").strip()
    ]

    evaluated_queries = len(valid_cases)

    if evaluated_queries == 0:
        raise ValueError(
            "No valid evaluation cases."
        )

    metrics = {
        "evaluation_queries":
            evaluated_queries,

        "Recall@1":
            round(
                hit_counts[1]
                / evaluated_queries,
                4
            ),

        "Recall@3":
            round(
                hit_counts[3]
                / evaluated_queries,
                4
            ),

        "Recall@5":
            round(
                hit_counts[5]
                / evaluated_queries,
                4
            ),

        "Recall@10":
            round(
                hit_counts[10]
                / evaluated_queries,
                4
            ),

        "Precision@1":
            round(
                precision_sums[1]
                / evaluated_queries,
                4
            ),

        "Precision@3":
            round(
                precision_sums[3]
                / evaluated_queries,
                4
            ),

        "Precision@5":
            round(
                precision_sums[5]
                / evaluated_queries,
                4
            ),

        "Precision@10":
            round(
                precision_sums[10]
                / evaluated_queries,
                4
            ),

        "MRR":
            round(
                sum(reciprocal_ranks)
                / len(reciprocal_ranks),
                4
            ),

        "average_adaptive_results":
            round(
                sum(adaptive_result_counts)
                / len(adaptive_result_counts),
                2
            ),

        "adaptive_min_results":
            min(adaptive_result_counts)
            if adaptive_result_counts
            else 0,

        "adaptive_max_results":
            max(adaptive_result_counts)
            if adaptive_result_counts
            else 0,

        "failed_queries":
            len(failures)
    }

    return metrics, failures


# ============================================================
# MAIN
# ============================================================

def run_evaluation():

    logger.info("=" * 70)
    logger.info("MEMORYLANE RETRIEVAL EVALUATION")
    logger.info("=" * 70)

    # --------------------------------------------------------
    # Load evaluation dataset
    # --------------------------------------------------------

    evaluation_path = Path(
        EVAL_DATA_PATH
    )

    if not evaluation_path.exists():
        raise FileNotFoundError(
            f"Evaluation file not found: "
            f"{evaluation_path.resolve()}"
        )

    with evaluation_path.open(
        "r",
        encoding="utf-8"
    ) as f:
        evaluation_data = json.load(f)

    if not isinstance(
        evaluation_data,
        list
    ):
        raise ValueError(
            "evaluation.json must contain a JSON list."
        )

    logger.info(
        f"Loaded {len(evaluation_data)} evaluation queries."
    )

    # --------------------------------------------------------
    # Initialize retriever
    # --------------------------------------------------------

    retriever = MemoryLaneRetriever()

    # --------------------------------------------------------
    # Evaluate
    # --------------------------------------------------------

    metrics, failures = calculate_metrics(
        retriever,
        evaluation_data
    )

    # --------------------------------------------------------
    # Print results
    # --------------------------------------------------------

    logger.info("")
    logger.info("=" * 70)
    logger.info("EVALUATION RESULTS")
    logger.info("=" * 70)

    for key, value in metrics.items():
        logger.info(
            f"{key}: {value}"
        )

    logger.info(
        "=" * 70
    )

    # --------------------------------------------------------
    # Save report
    # --------------------------------------------------------

    report = {
        "metrics": metrics,
        "config": {
            "embedding_model":
                EMBEDDING_MODEL_NAME,

            "reranker_model":
                RERANKER_MODEL_NAME,

            "candidate_k":
                CANDIDATE_K,

            "semantic_weight":
                SEMANTIC_WEIGHT,

            "bm25_weight":
                BM25_WEIGHT,

            "metric_ks":
                METRIC_KS,

            "adaptive_cutoff":
                "largest reranker-score drop"
        },

        "failures": failures
    }

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False
        )

    logger.info(
        f"Report saved to: {OUTPUT_PATH}"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run_evaluation()