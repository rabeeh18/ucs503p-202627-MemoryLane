"""Evaluate hybrid retrieval with Recall@k and MRR.

Usage (from project root):
    python -m evaluation.evaluate
    python -m evaluation.evaluate --eval-file evaluation/evaluation.json --top-k 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.retrieval import hybrid_search
from backend.url_utils import normalize_url


def recall_at_k(ranked_urls: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    hit = any(url in relevant for url in ranked_urls[:k])
    return 1.0 if hit else 0.0


def reciprocal_rank(ranked_urls: list[str], relevant: set[str]) -> float:
    for i, url in enumerate(ranked_urls, start=1):
        if url in relevant:
            return 1.0 / i
    return 0.0


def evaluate(eval_path: Path, top_k: int, candidate_pool: int) -> dict:
    payload = json.loads(eval_path.read_text(encoding="utf-8"))
    queries = payload.get("queries", [])

    ks = [1, 3, 5, 10]
    totals = {k: 0.0 for k in ks}
    mrr_total = 0.0
    details = []

    for item in queries:
        query = item["query"]
        relevant = {normalize_url(u) for u in item.get("relevant_urls", [])}
        results = hybrid_search(query, top_k=max(top_k, 10), candidate_pool=candidate_pool)
        ranked = [normalize_url(r.get("url", "")) for r in results]

        row = {
            "id": item.get("id"),
            "query": query,
            "ranked_urls": ranked[:top_k],
        }
        for k in ks:
            value = recall_at_k(ranked, relevant, k)
            totals[k] += value
            row[f"recall@{k}"] = value
        rr = reciprocal_rank(ranked, relevant)
        mrr_total += rr
        row["rr"] = rr
        details.append(row)

    n = max(len(queries), 1)
    metrics = {f"recall@{k}": totals[k] / n for k in ks}
    metrics["mrr"] = mrr_total / n
    metrics["n_queries"] = len(queries)
    return {"metrics": metrics, "details": details}


def main():
    parser = argparse.ArgumentParser(description="Evaluate MemoryLane hybrid retrieval")
    parser.add_argument("--eval-file", default=str(ROOT / "evaluation" / "evaluation.json"))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--candidates", type=int, default=30)
    parser.add_argument("--out", default=str(ROOT / "evaluation" / "evaluation_report.json"))
    args = parser.parse_args()

    report = evaluate(Path(args.eval_file), args.top_k, args.candidates)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("MemoryLane evaluation")
    print("-" * 32)
    for key, value in report["metrics"].items():
        if isinstance(value, float):
            print(f"{key}: {value:.4f}")
        else:
            print(f"{key}: {value}")
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
