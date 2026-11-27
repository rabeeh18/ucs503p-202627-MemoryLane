"""Record what the server's search returns for the parity queries.

Runs backend.retrieval.hybrid_search (the code behind POST /search) against the
throwaway Solr core that solr_corpus.py filled, with a fixed "now" so time
phrases resolve the same way in both engines, and writes the results for
hybrid_check.mjs to compare with the browser engine.

Usage (from code/src): python -m evaluation.parity.server_results --solr http://localhost:8984/solr/parity --out <file>
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from backend import retrieval
from backend.query_intent import parse_query
from backend.solr_client import SolrClient
from evaluation.parity.solr_corpus import USER

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)

EXTRA_QUERIES = [
    "stem cells", "scifact pages about cancer", "what I read on scifact", "from october 2026",
    "articles from 3 october", "insulin resistance from last week", "DNA repair 2 weeks ago",
    "https://scifact.org/doc/40349336", "scifact.org", "the of and", "gene therapy -mice",
    "\"immune response\"", "vitamin D", "malaria in africa", "obesity and diabetes in children",
    "a b c", "PCSK9 inhibitors decrease plasma Lp(a) levels.", "blood pressure today",
]


def queries(path: Path) -> list[str]:
    claims = [q["text"] for q in json.loads(path.read_text(encoding="utf-8"))]
    return claims + EXTRA_QUERIES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solr", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--queries", default="evaluation/scifact_data/queries.json")
    ap.add_argument("--top-k", type=int, default=10)
    args = ap.parse_args()

    retrieval.parse_query = lambda q, domains, now=None: parse_query(q, domains, now=NOW)
    solr = SolrClient(args.solr)
    out = {"now": NOW.isoformat(), "top_k": args.top_k, "results": {}}
    for q in queries(Path(args.queries)):
        results = retrieval.hybrid_search(q, USER, top_k=args.top_k, solr=solr)
        out["results"][q] = [
            {"page_id": r["page_id"], "rank": r["rank"], "snippet": r["snippet"],
             "fused_score": r["fused_score"], "vector_similarity": r["vector_similarity"]}
            for r in results
        ]
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{len(out['results'])} queries recorded")


if __name__ == "__main__":
    main()
