"""Build a parity corpus and load it into a throwaway Solr core.

The local (browser) engine must rank exactly as the server's Solr does. This
writes the SciFact abstracts, cleaned and chunked by the server's own code, to
a JSON file the JavaScript checks read, and indexes the same chunks (with their
server-side embeddings) into a Solr core created with scripts/setup_solr.sh.

Usage (from code/src, Solr on port 8984 with a core named "parity"):
    python -m evaluation.parity.solr_corpus --solr http://localhost:8984/solr/parity --out evaluation/parity/corpus_chunks.json
"""
import argparse
import json
from pathlib import Path

import httpx

from backend.chunking import chunk_text
from backend.cleaning import clean_content
from backend.embeddings import embed_passages

USER = "parity-user"


def build(corpus_path: Path, limit: int | None):
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))[:limit]
    docs = []
    for n, page in enumerate(corpus):
        page_id = f"p{n:04d}"
        text = clean_content(None, page["content"])
        for i, chunk in enumerate(chunk_text(text)):
            docs.append({
                "id": f"{page_id}::{i}", "user_id": USER, "page_id": page_id, "chunk_id": i,
                "title": page["title"], "text": chunk, "url": page["url"],
                "domain": "scifact.org", "timestamp": f"2026-10-{1 + n % 28:02d}T12:00:00Z",
            })
    return docs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solr", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--corpus", default="evaluation/scifact_data/corpus.json")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    docs = build(Path(args.corpus), args.limit)
    vectors = embed_passages([f"{d['title']}\n\n{d['text']}" for d in docs])
    client = httpx.Client(timeout=120)
    client.post(f"{args.solr}/update?commit=true", json={"delete": {"query": "*:*"}}).raise_for_status()
    for start in range(0, len(docs), 200):
        batch = [{**d, "embedding": v} for d, v in zip(docs[start:start + 200], vectors[start:start + 200])]
        client.post(f"{args.solr}/update", json=batch).raise_for_status()
    client.post(f"{args.solr}/update?commit=true", json={}).raise_for_status()
    out = [{**d, "embedding": [round(x, 7) for x in v]} for d, v in zip(docs, vectors)]
    Path(args.out).write_text(json.dumps(out), encoding="utf-8")
    print(f"{len(docs)} chunks from {len({d['page_id'] for d in docs})} pages written and indexed")


if __name__ == "__main__":
    main()
