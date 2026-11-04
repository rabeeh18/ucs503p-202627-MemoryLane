r"""Generate evaluation queries from indexed pages.

Usage (from code/src):
    python -m evaluation.generate_eval             # title queries for the eval core

For your own library on the server:
    # which user id is yours (page counts per user)
    docker compose exec -T backend python -m evaluation.generate_eval --core memorylane_v2 --list-users

    # a starting set: a random sample of your pages with the query left empty
    docker compose exec -T backend python -m evaluation.generate_eval --core memorylane_v2 \
        --user-id <your user id> --starter --limit 50 --out - > evaluation/personal.json

Fill in each `query` the way you would really search for that page, set its
`category`, and delete the pages you don't remember. Title queries (the default
mode) are near-certain hits for keyword search, so they say little about
precision; the starter set is meant to be written by hand.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.solr_client import user_filter
from evaluation.common import add_core_args, eval_solr
from evaluation.evaluate import CATEGORIES

# Pages read when sampling a starter set.
STARTER_SCAN_LIMIT = 5000


def generate(limit: int, solr, user_id: str) -> dict:
    url = f"{solr.base_url}/select"
    params = {
        "q": "*:*",
        "fq": user_filter(user_id),
        "fl": "url,title,text,page_id",
        "rows": limit,
        "sort": "timestamp desc",
        "wt": "json",
        "group": "true",
        "group.field": "page_id",
        "group.limit": 1,
    }
    response = solr.client.get(url, params=params)
    response.raise_for_status()
    groups = response.json().get("grouped", {}).get("page_id", {}).get("groups", [])

    queries = []
    for i, group in enumerate(groups, start=1):
        docs = group.get("doclist", {}).get("docs", [])
        if not docs:
            continue
        doc = docs[0]
        title = (doc.get("title") or "").strip()
        text = (doc.get("text") or "").strip()
        url_value = doc.get("url") or ""
        if not title or not url_value:
            continue
        snippet = " ".join(text.split()[:12])
        query = title if len(title.split()) >= 3 else f"{title} {snippet}".strip()
        queries.append({
            "id": f"auto_{i}",
            "query": query,
            "relevant_urls": [url_value],
        })

    return {"queries": queries}


def starter(limit: int, solr, user_id: str, seed: int = 0) -> dict:
    """A random sample of the user's pages, each with an empty query to fill in."""
    pages = [p for p in solr.scan_page_heads(user_id, "url,title,domain", STARTER_SCAN_LIMIT)
             if p.get("url")]
    sample = random.Random(seed).sample(pages, min(limit, len(pages)))
    return {
        "categories": CATEGORIES,
        "queries": [{
            "id": f"p{i}",
            "category": "",
            "query": "",
            "relevant_urls": [page["url"]],
            "title": (page.get("title") or "").strip(),
        } for i, page in enumerate(sample, start=1)],
    }


def list_users(solr) -> list[tuple[str, int]]:
    """Every user id in the core with its number of pages, most pages first."""
    data = solr._select({
        "q": "*:*",
        "fq": "chunk_id:0",
        "rows": 0,
        "facet": "true",
        "facet.field": "user_id",
        "facet.limit": -1,
        "facet.mincount": 1,
    })
    flat = data.get("facet_counts", {}).get("facet_fields", {}).get("user_id", [])
    return sorted(zip(flat[::2], flat[1::2]), key=lambda pair: -pair[1])


def main():
    parser = argparse.ArgumentParser(description="Generate evaluation data from Solr")
    parser.add_argument("--limit", type=int, default=25)
    add_core_args(parser)
    parser.add_argument("--starter", action="store_true",
                        help="Sample pages with empty queries, to write by hand")
    parser.add_argument("--seed", type=int, default=0, help="Sampling seed for --starter")
    parser.add_argument("--list-users", action="store_true",
                        help="Print each user id in the core with its page count, then exit")
    parser.add_argument("--out", default=str(ROOT / "evaluation" / "evaluation.json"),
                        help='Output file, or "-" for stdout')
    args = parser.parse_args()

    solr = eval_solr(args)
    if args.list_users:
        for user_id, pages in list_users(solr):
            print(f"{pages:>6}  {user_id}")
        return

    if args.starter:
        payload = starter(args.limit, solr, args.user_id, args.seed)
    else:
        payload = generate(args.limit, solr, args.user_id)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.out == "-":
        sys.stdout.write(text)
    else:
        Path(args.out).write_text(text, encoding="utf-8")
    print(f"Wrote {len(payload['queries'])} queries to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
