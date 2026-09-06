# Evaluation Results

The retrieval evaluation produced the following results.

| Method | MRR@10 | Recall@10 | nDCG@10 |
| --- | ---: | ---: | ---: |
| BM25 Only | 0.6482 | 0.8117 | 0.6776 |
| Vector Only | **0.7795** | 0.8867 | **0.8008** |
| Combined Retrieval | 0.7538 | **0.9167** | 0.7890 |

## What the results show

### BM25

BM25 provides a useful lexical baseline and remains effective when query terminology matches stored content.

### Vector retrieval

Vector retrieval achieved the highest MRR@10 and nDCG@10 on the selected benchmark. This indicates strong performance in placing relevant scientific content near the top of the ranking.

### Combined retrieval

Combined retrieval achieved the highest Recall@10. It retrieved the largest proportion of relevant documents within the top ten.

The results therefore do not show one method winning every metric. Different retrieval approaches have different strengths on the selected corpus and queries.
