r"""Evaluate hybrid retrieval with Recall@k and MRR, per query category.

Usage (from code/src):
    python -m evaluation.evaluate
    python -m evaluation.evaluate --eval-file evaluation/evaluation.json --top-k 10 [--core memorylane_eval]

On the server, against your own library (the file goes in on stdin and the
report comes out on stdout, so nothing is written inside the container):
    docker compose exec -T backend python -m evaluation.evaluate \
        --core memorylane_v2 --user-id <your user id> --eval-file - --out - \
        < evaluation/personal.json > evaluation/personal_report.json

Eval file format:
    {"queries": [{"id": "p1", "category": "site", "query": "reddit post on rust lifetimes",
                  "relevant_urls": ["https://www.reddit.com/r/rust/comments/..."]}]}

`category` is optional (see CATEGORIES). Queries left empty are skipped. An
expected URL that isn't a saved page of that user is reported and the query is
left out of the metrics, since no ranking change could ever find it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.url_utils import generate_page_id, normalize_url
from evaluation.common import add_core_args, eval_solr

KS = [1, 3, 5, 10]

# How the person remembers the page. Free text is allowed; these are the usual ones.
CATEGORIES = {
    "navigational": "names the page: its title or what it is called",
    "site": "names the site it was on (reddit, github, a docs site...)",
    "topic": "only what it was about, in your own words",
    "time": "says when you saw it (yesterday, last week, in March...)",
}
UNCATEGORISED = "uncategorised"


def log(message: str) -> None:
    print(message, file=sys.stderr)


def recall_at_k(ranked_urls: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    hit = any(url in relevant for url in ranked_urls[:k])
    return 1.0 if hit else 0.0


def reciprocal_rank(ranked_urls: list[str], relevant: set[str]) -> float:
    rank = first_rank(ranked_urls, relevant)
    return 1.0 / rank if rank else 0.0


def first_rank(ranked_urls: list[str], relevant: set[str]) -> int | None:
    for i, url in enumerate(ranked_urls, start=1):
        if url in relevant:
            return i
    return None


def load_queries(eval_file: str) -> list[dict]:
    """Queries from a file, or from stdin when `eval_file` is "-"."""
    text = sys.stdin.read() if eval_file == "-" else Path(eval_file).read_text(encoding="utf-8")
    payload = json.loads(text)
    return payload.get("queries", []) if isinstance(payload, dict) else payload


def missing_urls(urls: set[str], solr, user_id: str) -> list[str]:
    """Normalised URLs that aren't saved pages of `user_id`."""
    return [u for u in sorted(urls)
            if solr.get_page_head(generate_page_id(user_id, u), user_id) is None]


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    metrics = {f"recall@{k}": (sum(r[f"recall@{k}"] for r in rows) / n if n else 0.0) for k in KS}
    metrics["mrr"] = sum(r["rr"] for r in rows) / n if n else 0.0
    metrics["n_queries"] = n
    return metrics


def evaluate(queries: list[dict], top_k: int, candidate_pool: int, solr, user_id: str,
             search=None) -> dict:
    if search is None:
        from backend.retrieval import hybrid_search as search

    details, skipped_empty, skipped_missing = [], [], []
    for i, item in enumerate(queries, start=1):
        query = (item.get("query") or "").strip()
        qid = item.get("id") or f"q{i}"
        relevant = {normalize_url(u) for u in item.get("relevant_urls", []) if u}
        if not query or not relevant:
            skipped_empty.append(qid)
            continue
        missing = missing_urls(relevant, solr, user_id)
        if missing and len(missing) == len(relevant):
            skipped_missing.append({"id": qid, "query": query, "missing_urls": missing})
            continue

        results = search(query, user_id, top_k=max(top_k, max(KS)),
                         candidate_pool=candidate_pool, solr=solr, snippets=False)
        ranked = [normalize_url(r.get("url", "")) for r in results]
        row = {
            "id": qid,
            "category": (item.get("category") or "").strip().lower() or UNCATEGORISED,
            "query": query,
            "rank": first_rank(ranked, relevant),
            "ranked_urls": ranked[:top_k],
        }
        if missing:
            row["missing_urls"] = missing
        for k in KS:
            row[f"recall@{k}"] = recall_at_k(ranked, relevant, k)
        row["rr"] = reciprocal_rank(ranked, relevant)
        details.append(row)

    categories = sorted({r["category"] for r in details})
    return {
        "metrics": summarise(details),
        "by_category": {c: summarise([r for r in details if r["category"] == c]) for c in categories},
        "skipped": {"empty": skipped_empty, "not_saved": skipped_missing},
        "details": details,
    }


def print_summary(report: dict) -> None:
    log("MemoryLane evaluation")
    log("-" * 60)
    header = f"{'':16}{'n':>4}" + "".join(f"{'R@' + str(k):>8}" for k in KS) + f"{'MRR':>8}"
    log(header)
    rows = [("all", report["metrics"])] + list(report["by_category"].items())
    for name, m in rows:
        log(f"{name:16}{m['n_queries']:>4}" + "".join(f"{m[f'recall@{k}']:>8.2f}" for k in KS)
            + f"{m['mrr']:>8.3f}")

    misses = [r for r in report["details"] if r["rank"] != 1]
    if misses:
        log("\nNot first:")
        for r in sorted(misses, key=lambda r: (r["rank"] is None, r["rank"] or 0)):
            where = f"#{r['rank']}" if r["rank"] else "not in top 10"
            log(f"  {r['id']:>6}  {where:>14}  [{r['category']}] {r['query']}")

    skipped = report["skipped"]
    if skipped["not_saved"]:
        log(f"\nWARNING: {len(skipped['not_saved'])} queries left out: their expected URL is not a saved page.")
        log("Check the URL is the one MemoryLane stored (open it from the Library page and copy that).")
        for s in skipped["not_saved"]:
            for u in s["missing_urls"]:
                log(f"  {s['id']:>6}  {u}")
    partial = [r for r in report["details"] if r.get("missing_urls")]
    for r in partial:
        log(f"WARNING: {r['id']}: some expected URLs are not saved pages: {', '.join(r['missing_urls'])}")
    if skipped["empty"]:
        log(f"\n{len(skipped['empty'])} queries not filled in yet, skipped.")


def main():
    parser = argparse.ArgumentParser(description="Evaluate MemoryLane hybrid retrieval")
    parser.add_argument("--eval-file", default=str(ROOT / "evaluation" / "evaluation.json"),
                        help='Eval file, or "-" for stdin')
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--candidates", type=int, default=50)
    add_core_args(parser)
    parser.add_argument("--out", default=str(ROOT / "evaluation" / "evaluation_report.json"),
                        help='Report file, or "-" for stdout')
    args = parser.parse_args()

    report = evaluate(load_queries(args.eval_file), args.top_k, args.candidates,
                      eval_solr(args), args.user_id)
    text = json.dumps(report, indent=2) + "\n"
    if args.out == "-":
        sys.stdout.write(text)
    else:
        Path(args.out).write_text(text, encoding="utf-8")
    print_summary(report)
    if args.out != "-":
        log(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
