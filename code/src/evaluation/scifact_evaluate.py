"""Evaluate retrieval on SciFact with the production search code.

Runs every query through `hybrid_search` (the function behind POST /search) in
five configurations and reports, for each:

  Quality        hit@1, hit@3, hit@10   share of queries with a right answer in the top 1 / 3 / 10
                 mrr@10                 how high the first right answer is, on average (1 = always first)
                 recall@10              share of all right answers found in the top 10
                 ndcg@10                how well the right answers are ordered in the top 10
                 map@10                 average precision over the top 10 (rewards finding all of them early)
  Behaviour      empty_rate             share of queries that got no results at all
                 avg_results            results returned per query (at most 10)
  Speed          latency_ms_p50/p95/mean  in-process search time per query (no network, no sign-in check)

and a 95% bootstrap interval for hit@1 and mrr@10, so small differences between
configurations can be told apart from noise (100 queries is a small sample).

Usage (from code/src, after evaluation.scifact_ingest):
    python -m evaluation.scifact_evaluate [--core memorylane_eval]
"""
import argparse
import json
import logging
import math
import random
import statistics
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import retrieval
from backend.config import EMBEDDING_MODEL
from backend.url_utils import normalize_url
from evaluation.common import add_core_args, eval_solr

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = ROOT / "evaluation" / "scifact_data"
QUERIES_JSON = DATA_DIR / "queries.json"
QRELS_JSON = DATA_DIR / "qrels.json"
REPORT_JSON = ROOT / "evaluation" / "scifact_report.json"

K = 10
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_SEED = 503

# name -> settings patched into backend.retrieval for that run
CONFIGURATIONS = {
    "Hybrid": {},
    "BM25 only": {"BM25_WEIGHT": 1.0, "VECTOR_WEIGHT": 0.0},
    "Vector only": {"BM25_WEIGHT": 0.0, "VECTOR_WEIGHT": 1.0},
    # The relevance floor drops weak meaning-only matches; this run keeps them,
    # to measure what the floor costs on SciFact.
    "Hybrid, no relevance floor": {"MIN_VECTOR_SIMILARITY": 0.0},
    # Until November 2026 a page's score added 0.3 x its second-best chunk's
    # score. This run puts that bonus back, to show what turning it off gained.
    "Hybrid, old second-chunk bonus (0.3)": {"PAGE_SECOND_CHUNK_WEIGHT": 0.3},
}


# ---- per-query metrics (binary relevance) ----------------------------------------

def first_hit_rank(ranked, relevant, k=K):
    """1-based rank of the first relevant result in the top k, or None."""
    for i, url in enumerate(ranked[:k]):
        if url in relevant:
            return i + 1
    return None


def mrr_at_k(ranked, relevant, k=K):
    rank = first_hit_rank(ranked, relevant, k)
    return 1.0 / rank if rank else 0.0


def hit_at_k(ranked, relevant, k):
    return 1.0 if first_hit_rank(ranked, relevant, k) else 0.0


def recall_at_k(ranked, relevant, k=K):
    if not relevant:
        return 0.0
    return sum(1 for url in ranked[:k] if url in relevant) / len(relevant)


def ndcg_at_k(ranked, relevant, k=K):
    if not relevant:
        return 0.0
    dcg = sum(1.0 / math.log2(i + 2) for i, url in enumerate(ranked[:k]) if url in relevant)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / idcg if idcg else 0.0


def average_precision_at_k(ranked, relevant, k=K):
    if not relevant:
        return 0.0
    hits, total = 0, 0.0
    for i, url in enumerate(ranked[:k]):
        if url in relevant:
            hits += 1
            total += hits / (i + 1)
    return total / min(len(relevant), k)


QUALITY = {
    "hit@1": lambda r, rel: hit_at_k(r, rel, 1),
    "hit@3": lambda r, rel: hit_at_k(r, rel, 3),
    "hit@10": lambda r, rel: hit_at_k(r, rel, 10),
    "mrr@10": mrr_at_k,
    "recall@10": recall_at_k,
    "ndcg@10": ndcg_at_k,
    "map@10": average_precision_at_k,
}


def percentile(values, p):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = (len(ordered) - 1) * p / 100
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def bootstrap_interval(values, samples=BOOTSTRAP_SAMPLES, seed=BOOTSTRAP_SEED):
    """95% interval of the mean by resampling queries with replacement."""
    if not values:
        return [0.0, 0.0]
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(samples))
    return [round(percentile(means, 2.5), 4), round(percentile(means, 97.5), 4)]


# ---- running -----------------------------------------------------------------------

def summarise(per_query):
    """Average the per-query rows into one report entry."""
    n = len(per_query)
    report = {name: round(sum(q[name] for q in per_query) / n, 4) for name in QUALITY}
    latencies = [q["latency_ms"] for q in per_query]
    report.update({
        "empty_rate": round(sum(1 for q in per_query if q["returned"] == 0) / n, 4),
        "avg_results": round(sum(q["returned"] for q in per_query) / n, 2),
        "latency_ms_p50": round(percentile(latencies, 50), 1),
        "latency_ms_p95": round(percentile(latencies, 95), 1),
        "latency_ms_mean": round(statistics.mean(latencies), 1),
        "ci95": {
            "hit@1": bootstrap_interval([q["hit@1"] for q in per_query]),
            "mrr@10": bootstrap_interval([q["mrr@10"] for q in per_query]),
        },
        "queries": n,
    })
    return report


def evaluate_configuration(name, settings, queries, qrels, solr, user_id):
    logger.info(f"--- {name} ---")
    # A fresh query-embedding cache per run, so no run gets another's vectors for free.
    retrieval._cached_query_embedding.cache_clear()
    patches = [patch(f"backend.retrieval.{key}", value) for key, value in settings.items()]
    for p in patches:
        p.start()
    try:
        per_query = []
        for i, query in enumerate(queries, start=1):
            relevant = {normalize_url(url) for url in qrels.get(query["id"], [])}
            start = time.perf_counter()
            results = retrieval.hybrid_search(query["text"], user_id, top_k=K, solr=solr)
            latency = (time.perf_counter() - start) * 1000
            ranked = [normalize_url(r["url"]) for r in results]
            row = {"id": query["id"], "returned": len(ranked), "latency_ms": latency,
                   "first_hit_rank": first_hit_rank(ranked, relevant)}
            row.update({metric: fn(ranked, relevant) for metric, fn in QUALITY.items()})
            per_query.append(row)
            if i % 25 == 0:
                logger.info(f"{name}: {i}/{len(queries)} queries")
    finally:
        for p in patches:
            p.stop()
    return summarise(per_query), per_query


def evaluate_all(args):
    solr = eval_solr(args)
    for path in (QUERIES_JSON, QRELS_JSON):
        if not path.exists():
            raise SystemExit(f"Not found: {path}")
    queries = json.loads(QUERIES_JSON.read_text(encoding="utf-8"))
    qrels = json.loads(QRELS_JSON.read_text(encoding="utf-8"))
    logger.info(f"Loaded {len(queries)} queries")

    # Warm up (model load, Solr caches) with every query once, untimed, so the
    # first configuration isn't slowed by cold caches and the speeds compare fairly.
    logger.info("Warming up")
    for query in queries:
        retrieval.hybrid_search(query["text"], args.user_id, top_k=K, solr=solr)

    report, ranks = {}, {}
    for name, settings in CONFIGURATIONS.items():
        report[name], per_query = evaluate_configuration(name, settings, queries, qrels, solr, args.user_id)
        ranks[name] = {q["id"]: q["first_hit_rank"] for q in per_query}

    out = {
        "settings": {
            "embedding_model": EMBEDDING_MODEL,
            "rrf_k": retrieval.RRF_K,
            "min_vector_similarity": retrieval.MIN_VECTOR_SIMILARITY,
            "keyword_full_match": retrieval.KEYWORD_FULL_MATCH,
            "query_intent": retrieval.QUERY_INTENT_ENABLED,
            "rerank": retrieval.RERANK_ENABLED,
            "page_second_chunk_weight": retrieval.PAGE_SECOND_CHUNK_WEIGHT,
            "top_k": K,
        },
        "results": report,
        "first_hit_rank_per_query": ranks,
    }
    REPORT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("\n" + "=" * 72)
    print(" SCIFACT RETRIEVAL EVALUATION")
    print("=" * 72)
    columns = list(QUALITY) + ["empty_rate", "latency_ms_p50", "latency_ms_p95"]
    print(f"{'':38}" + "".join(f"{c:>12}" for c in columns))
    for name, metrics in report.items():
        print(f"{name:38}" + "".join(f"{metrics[c]:>12}" for c in columns))
    print("\n95% intervals (bootstrap):")
    for name, metrics in report.items():
        print(f"  {name:28} hit@1 {metrics['ci95']['hit@1']}  mrr@10 {metrics['ci95']['mrr@10']}")
    print(f"\nWritten to {REPORT_JSON}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate retrieval on SciFact")
    add_core_args(parser)
    evaluate_all(parser.parse_args())
