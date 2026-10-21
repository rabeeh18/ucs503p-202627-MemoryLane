# Evaluation Results

!!! note "Which version these numbers come from"
    These results were measured on the **earlier retrieval pipeline**: `all-MiniLM-L6-v2` embeddings, 300–500-word chunks, and min-max score fusion (0.5 / 0.5). The current pipeline (`bge-small-en-v1.5`, 150-word overlapping chunks with titles, Reciprocal Rank Fusion, a relevance floor) has not been re-benchmarked yet. Run the commands in [Methodology](methodology.md) to measure it.

| Method | MRR@10 | Recall@10 | nDCG@10 |
| --- | ---: | ---: | ---: |
| BM25 only | 0.6482 | 0.8117 | 0.6776 |
| Vector only | **0.7795** | 0.8867 | **0.8008** |
| Hybrid (min-max fusion) | 0.7538 | **0.9167** | 0.7890 |

## What the results show

### BM25

A solid lexical baseline. It works well when the query uses the same terms as the document.

### Vector retrieval

Vector retrieval had the best MRR@10 and nDCG@10: it put a relevant abstract at the top most often.

### Hybrid retrieval

Hybrid retrieval had the best Recall@10: it found the largest share of relevant abstracts in the top ten. Its MRR@10 and nDCG@10 were slightly below vector-only, so mixing in BM25 scores sometimes moved the first relevant result down a place.

No single method won every metric, which motivated the later changes:

- **Reciprocal Rank Fusion**, which combines ranks instead of raw scores
- A **stronger embedding model** (BGE) with a search instruction for queries
- **Smaller, overlapping chunks** embedded with the page title
- A **relevance floor**, so weak vector-only matches are dropped instead of shown
