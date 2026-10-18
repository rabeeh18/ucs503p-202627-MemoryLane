"""Generate evaluation.json from currently indexed Solr documents.

Usage (from project root):
    python -m evaluation.generate_eval
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.solr_client import user_filter
from evaluation.common import add_core_args, eval_solr


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


def main():
    parser = argparse.ArgumentParser(description="Generate evaluation data from Solr")
    parser.add_argument("--limit", type=int, default=25)
    add_core_args(parser)
    parser.add_argument("--out", default=str(ROOT / "evaluation" / "evaluation.json"))
    args = parser.parse_args()

    payload = generate(args.limit, eval_solr(args), args.user_id)
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(payload['queries'])} queries to {args.out}")


if __name__ == "__main__":
    main()
