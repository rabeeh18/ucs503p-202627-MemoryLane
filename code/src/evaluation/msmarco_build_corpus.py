import json
import random
from pathlib import Path

from datasets import load_dataset

from backend.url_utils import normalize_url

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "evaluation" / "msmarco_data"

TARGET_QUERIES = 100
TARGET_DOCS = 1000
SEED = 42


def main():
    random.seed(SEED)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading SciFact...")

    corpus = load_dataset("BeIR/scifact", "corpus", split="corpus")
    queries = load_dataset("BeIR/scifact", "queries", split="queries")
    qrels = load_dataset("BeIR/scifact-qrels", split="train")

    docs = {
        str(row["_id"]): {
            "url": f"https://scifact.org/doc/{row['_id']}",
            "title": row["title"],
            "content": row["text"],
        }
        for row in corpus
    }

    query_map = {
        str(row["_id"]): row["text"]
        for row in queries
    }

    relevant = {}

    for row in qrels:
        qid = str(row["query-id"])
        did = str(row["corpus-id"])

        if row["score"] > 0 and qid in query_map and did in docs:
            relevant.setdefault(qid, set()).add(did)

    valid_queries = [
        qid for qid, doc_ids in relevant.items()
        if doc_ids
    ]

    random.shuffle(valid_queries)

    selected = []
    required_docs = set()

    for qid in valid_queries:
        new_docs = required_docs | relevant[qid]

        if len(new_docs) <= TARGET_DOCS:
            selected.append(qid)
            required_docs = new_docs

        if len(selected) == TARGET_QUERIES:
            break

    if len(selected) < TARGET_QUERIES:
        raise RuntimeError(
            f"Could only select {len(selected)} queries."
        )

    print(f"Selected {len(selected)} queries.")
    print(f"Relevant documents: {len(required_docs)}")

    if len(required_docs) > TARGET_DOCS:
        raise RuntimeError("Relevant documents exceed corpus size.")

    # Fill remaining corpus with random distractors.
    candidates = [
        did for did in docs
        if did not in required_docs
    ]

    random.shuffle(candidates)

    final_ids = list(required_docs)
    final_ids.extend(candidates[:TARGET_DOCS - len(final_ids)])

    # Ensure normalized URLs are unique.
    final_docs = []
    seen_urls = set()

    for did in final_ids:
        doc = docs[did]
        norm = normalize_url(doc["url"])

        if norm in seen_urls:
            continue

        seen_urls.add(norm)
        final_docs.append(doc)

        if len(final_docs) == TARGET_DOCS:
            break

    if len(final_docs) != TARGET_DOCS:
        raise RuntimeError(
            f"Could only build {len(final_docs)} unique URLs."
        )

    corpus_urls = {
        normalize_url(doc["url"])
        for doc in final_docs
    }

    final_qrels = {}

    for qid in selected:
        urls = [
            normalize_url(docs[did]["url"])
            for did in relevant[qid]
            if did in docs
        ]

        urls = [url for url in urls if url in corpus_urls]

        if not urls:
            raise RuntimeError(
                f"Query {qid} has no relevant document in final corpus."
            )

        final_qrels[qid] = urls

    final_queries = [
        {
            "id": qid,
            "text": query_map[qid],
        }
        for qid in selected
    ]

    with open(DATA_DIR / "corpus.json", "w", encoding="utf-8") as f:
        json.dump(final_docs, f, indent=2)

    with open(DATA_DIR / "queries.json", "w", encoding="utf-8") as f:
        json.dump(final_queries, f, indent=2)

    with open(DATA_DIR / "qrels.json", "w", encoding="utf-8") as f:
        json.dump(final_qrels, f, indent=2)

    print("SUCCESS")
    print(f"Corpus:  {len(final_docs)} documents")
    print(f"Queries: {len(final_queries)}")
    print(f"Qrels:   {len(final_qrels)}")


if __name__ == "__main__":
    main()