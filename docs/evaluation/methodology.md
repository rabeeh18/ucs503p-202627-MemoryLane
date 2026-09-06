# Evaluation Methodology

MemoryLane's retrieval implementation was evaluated using the SciFact information-retrieval dataset adapted to the MemoryLane data model.

## Evaluation corpus

The evaluation setup used:

- 1,000 unique documents
- 100 evaluation queries
- 106 relevant documents in the selected relevance data

The documents were passed through the actual MemoryLane `/memory` endpoint rather than being inserted directly into Solr.

This means the benchmark exercised the application's processing pipeline, including URL handling, content processing, chunking, embedding generation, and indexing.

## Benchmark URLs

The benchmark documents use synthetic URLs of the form:

```text
https://scifact.org/doc/{document_id}
```

These URLs provide unique identifiers for the evaluation documents. The actual document titles and scientific content originate from SciFact.

The experiment is therefore a controlled retrieval benchmark rather than a live-web crawling evaluation.

## Configurations

Three retrieval configurations were compared:

### BM25 Only

Uses lexical retrieval without the semantic contribution.

### Vector Only

Uses dense semantic retrieval without the lexical contribution.

### Combined Retrieval

Uses the production configuration combining lexical and semantic retrieval signals.

## Metrics

The evaluation reports:

- **MRR@10** — how early the first relevant result appears.
- **Recall@10** — how much of the relevant set is retrieved in the top ten.
- **nDCG@10** — the quality of the ranking of relevant results.

Relevance was binary for this experiment.
