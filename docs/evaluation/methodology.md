# Evaluation Methodology

MemoryLane's retrieval is evaluated on **SciFact**, a scientific-claim retrieval dataset from the BEIR benchmark, adapted to MemoryLane's data model.

## Corpus and queries

- **1,000** SciFact abstracts as documents
- **100** claims as queries
- **106** relevant documents across 115 query–document pairs (binary relevance)

Each document gets a synthetic URL of the form:

```text
https://scifact.org/doc/{document_id}
```

The URLs only give each document a unique identity; titles and text come from SciFact. This is a controlled retrieval benchmark, not a live-web crawl.

## How it runs

The evaluation uses the same code as production:

- Documents are saved through `ingest_page`, the same function behind `POST /memory`, so cleaning, chunking, embedding and indexing are all exercised.
- Queries go through `hybrid_search`, the same function behind `POST /search`.
- Everything runs under the user id `eval`, in a **separate core** (`memorylane_eval` by default), so benchmark data never mixes with real users.

```bash
cd code/src
CORE_NAME=memorylane_eval ./scripts/setup_solr.sh
python -m evaluation.scifact_ingest      # index the 1,000 documents
python -m evaluation.scifact_evaluate    # writes evaluation/scifact_report.json
```

## Configurations compared

| Configuration | What it uses |
| --- | --- |
| **BM25 only** | Lexical retrieval |
| **Vector only** | Dense retrieval |
| **Hybrid** | The production pipeline: both, fused |

## Metrics

- **MRR@10**: how early the first relevant result appears
- **Recall@10**: how much of the relevant set is in the top ten
- **nDCG@10**: how well the relevant results are ordered

Relevant URLs are compared after normalisation.

## Second evaluation: generated queries

`evaluation/generate_eval.py` builds queries from pages already indexed, and `evaluation/evaluate.py` reports Recall@1/3/5/10 and MRR for them. This is a quick check on your own data rather than a benchmark.
