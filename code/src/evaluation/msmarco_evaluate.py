import json
import logging
import math
import sys
from pathlib import Path
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import API_PORT
from backend.url_utils import normalize_url
from backend.retrieval import hybrid_search

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

DATA_DIR = ROOT / "evaluation" / "msmarco_data"

QUERIES_JSON = DATA_DIR / "queries.json"
QRELS_JSON = DATA_DIR / "qrels.json"

REPORT_JSON = ROOT / "evaluation" / "msmarco_report.json"

# The backend listens on 0.0.0.0,
# but clients must connect through localhost.
BASE_URL = f"http://localhost:{API_PORT}"


def mrr_at_k(ranked_urls, relevant_urls, k=10):
    """
    Mean Reciprocal Rank contribution for one query.
    """
    for i, url in enumerate(ranked_urls[:k]):
        if url in relevant_urls:
            return 1.0 / (i + 1)

    return 0.0


def recall_at_k(ranked_urls, relevant_urls, k=10):
    """
    Recall@K = relevant documents retrieved in top K /
               total relevant documents.
    """
    if not relevant_urls:
        return 0.0

    hits = sum(
        1 for url in ranked_urls[:k]
        if url in relevant_urls
    )

    return hits / len(relevant_urls)


def ndcg_at_k(ranked_urls, relevant_urls, k=10):
    """
    Binary-relevance nDCG@K.
    """
    if not relevant_urls:
        return 0.0

    # DCG
    dcg = 0.0

    for i, url in enumerate(ranked_urls[:k]):
        if url in relevant_urls:
            dcg += 1.0 / math.log2(i + 2)

    # Ideal DCG
    ideal_hits = min(len(relevant_urls), k)

    idcg = 0.0

    for i in range(ideal_hits):
        idcg += 1.0 / math.log2(i + 2)

    if idcg == 0:
        return 0.0

    return dcg / idcg


def evaluate_run(queries, qrels, name, search_fn):
    """
    Run one retrieval method over all queries
    and calculate average metrics.
    """

    logger.info(f"--- Running Evaluation: {name} ---")

    metrics = {
        "mrr@10": 0.0,
        "recall@10": 0.0,
        "ndcg@10": 0.0
    }

    n = len(queries)

    if n == 0:
        return metrics

    for i, query_item in enumerate(queries, start=1):

        q_id = query_item["id"]
        q_text = query_item["text"]

        relevant = set(
            normalize_url(url)
            for url in qrels.get(q_id, [])
        )

        ranked = search_fn(q_text)

        metrics["mrr@10"] += mrr_at_k(
            ranked,
            relevant,
            k=10
        )

        metrics["recall@10"] += recall_at_k(
            ranked,
            relevant,
            k=10
        )

        metrics["ndcg@10"] += ndcg_at_k(
            ranked,
            relevant,
            k=10
        )

        if i % 10 == 0:
            logger.info(
                f"{name}: evaluated {i}/{n} queries..."
            )

    metrics = {
        key: value / n
        for key, value in metrics.items()
    }

    logger.info(
        f"{name} Metrics: {metrics}"
    )

    return metrics


def run_hybrid_api(query_text):
    """
    End-to-end evaluation through the real MemoryLane API.
    """

    try:

        response = httpx.post(
            f"{BASE_URL}/search",
            json={
                "query": query_text,
                "num_results": 10,
                "summarize": False,
                "debug": False
            },
            timeout=30.0
        )

        response.raise_for_status()

        data = response.json()

        return [
            normalize_url(item["url"])
            for item in data.get("results", [])
        ]

    except Exception as e:

        logger.error(
            f"API Error for query '{query_text}': {e}"
        )

        return []


def run_bm25(query_text):
    """
    BM25-only ablation.
    """

    with patch(
        "backend.retrieval.BM25_WEIGHT",
        1.0
    ), patch(
        "backend.retrieval.VECTOR_WEIGHT",
        0.0
    ):

        results = hybrid_search(
            query_text,
            top_k=10
        )

        return [
            normalize_url(r["url"])
            for r in results
        ]


def run_vector(query_text):
    """
    Vector-only ablation.
    """

    with patch(
        "backend.retrieval.BM25_WEIGHT",
        0.0
    ), patch(
        "backend.retrieval.VECTOR_WEIGHT",
        1.0
    ):

        results = hybrid_search(
            query_text,
            top_k=10
        )

        return [
            normalize_url(r["url"])
            for r in results
        ]


def evaluate_all():

    if not QUERIES_JSON.exists():
        logger.error(
            f"Queries file not found: {QUERIES_JSON}"
        )
        sys.exit(1)

    if not QRELS_JSON.exists():
        logger.error(
            f"Qrels file not found: {QRELS_JSON}"
        )
        sys.exit(1)

    # Load queries
    with open(
        QUERIES_JSON,
        "r",
        encoding="utf-8"
    ) as f:
        queries = json.load(f)

    # Load ground truth
    with open(
        QRELS_JSON,
        "r",
        encoding="utf-8"
    ) as f:
        qrels = json.load(f)

    logger.info(
        f"Loaded {len(queries)} queries."
    )

    report = {}

    # -------------------------------------------------
    # 1. Hybrid Search — real HTTP API
    # -------------------------------------------------

    report["Hybrid (API)"] = evaluate_run(
        queries,
        qrels,
        "Hybrid (API)",
        run_hybrid_api
    )

    # -------------------------------------------------
    # 2. BM25 only
    # -------------------------------------------------

    report["BM25 Only"] = evaluate_run(
        queries,
        qrels,
        "BM25 Only",
        run_bm25
    )

    # -------------------------------------------------
    # 3. Vector only
    # -------------------------------------------------

    report["Vector Only"] = evaluate_run(
        queries,
        qrels,
        "Vector Only",
        run_vector
    )

    # -------------------------------------------------
    # Save report
    # -------------------------------------------------

    with open(
        REPORT_JSON,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            report,
            f,
            indent=2
        )

    # -------------------------------------------------
    # Print results
    # -------------------------------------------------

    print()
    print("=" * 50)
    print(" SCIFACT RETRIEVAL EVALUATION RESULTS ")
    print("=" * 50)

    for method, metrics in report.items():

        print()
        print(f"[{method}]")

        for metric, value in metrics.items():

            print(
                f"  {metric}: {value:.4f}"
            )

    print()
    print("=" * 50)


if __name__ == "__main__":
    evaluate_all()