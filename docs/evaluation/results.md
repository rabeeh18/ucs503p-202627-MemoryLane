# Evaluation Results

These are SciFact results for the **current** search: `bge-small-en-v1.5`, 150-word overlapping chunks embedded with the page title, Reciprocal Rank Fusion, the relevance floor, and pages scored by their best chunk. They were measured on 19 November 2026 with `evaluation.scifact_evaluate` (see [Methodology](methodology.md)): 100 claims over 999 indexed abstracts. One of the 1,000 abstracts failed to index, and it isn't the answer to any claim.

## Current search

| Configuration | Hit@1 | Hit@3 | Hit@10 | MRR@10 | Recall@10 | nDCG@10 | MAP@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Hybrid (live search)** | 0.71 | 0.84 | 0.93 | 0.786 | 0.922 | 0.810 | 0.768 |
| BM25 only | 0.63 | 0.76 | 0.86 | 0.705 | 0.837 | 0.728 | 0.687 |
| Vector only | **0.75** | **0.86** | **0.94** | **0.812** | **0.932** | **0.837** | **0.803** |
| Hybrid, no relevance floor | 0.71 | 0.84 | 0.93 | 0.785 | 0.922 | 0.810 | 0.768 |
| Hybrid, old second-chunk bonus (0.3) | 0.44 | 0.73 | 0.92 | 0.601 | 0.897 | 0.663 | 0.578 |

In plain words:

- **Hit@1**: how often the right abstract is the very first result. **Hit@3** and **Hit@10** are the same for the top 3 and the top 10.
- **MRR@10**: how high the first right result is, on average. 1.0 means always first; 0.5 means second on average.
- **Recall@10**: the share of all right abstracts that appear in the top ten (some claims have more than one).
- **nDCG@10** and **MAP@10**: how well all the right results are ordered, with mistakes near the top counting most.

No claim got an empty result list in any configuration. Hybrid search took about **75 ms** per query in the middle case and **90 ms** for the slowest 5% (on a laptop, inside the backend process; network and sign-in checks aren't included).

### How sure are these numbers?

With only 100 claims, some of the variation is luck. A bootstrap (resampling the claims 2,000 times) gives these 95% ranges:

| Configuration | Hit@1 | MRR@10 |
| --- | --- | --- |
| Hybrid (live search) | 0.62 – 0.79 | 0.72 – 0.85 |
| BM25 only | 0.54 – 0.72 | 0.63 – 0.78 |
| Vector only | 0.67 – 0.83 | 0.75 – 0.88 |
| Hybrid, old second-chunk bonus (0.3) | 0.34 – 0.54 | 0.53 – 0.68 |

The old bonus's range doesn't overlap the live search's, so turning it off is a real gain. Hybrid and vector-only overlap almost completely, so the small gap between them may be luck.

## What the results show

### Scoring a page by its best chunk

Until November 2026, a page's score was its best chunk's score plus 0.3 times its second-best chunk's score (`PAGE_SECOND_CHUNK_WEIGHT`). This was meant to favour pages that match in more than one place. With Reciprocal Rank Fusion, though, the scores of neighbouring results are very close: rank 1 scores 1/61 and rank 10 scores 1/70. A bonus of 0.3 × 1/62 is bigger than that whole gap, so **a longer page with two matching chunks beat a shorter page that matched better**. When that search got the first result wrong, the page it put first had 2.1 chunks on average; the right answers had 1.3.

Every bonus size tried made ranking worse:

| Bonus | Hit@1 | MRR@10 | nDCG@10 |
| --- | ---: | ---: | ---: |
| 0.3 (before) | 0.44 | 0.601 | 0.663 |
| 0.1 | 0.56 | 0.701 | 0.741 |
| 0.05 | 0.64 | 0.749 | 0.783 |
| 0.02 | 0.71 | 0.786 | 0.810 |
| **0 (now)** | 0.71 | 0.786 | 0.810 |

So the weight is now **0**, and a page is scored by its best-matching chunk alone. The bonus held back BM25-only and vector-only runs just as much: they went from MRR@10 0.414 and 0.455 to 0.705 and 0.812.

### The relevance floor costs nothing here

Turning the floor off changed almost nothing (MRR@10 0.786 → 0.785), and no claim lost all its results. The floor only drops weak vector-only matches, and the right abstract is rarely one of them.

### Hybrid and vector-only are level on SciFact

Vector-only is slightly ahead (MRR@10 0.812 against 0.786), within the margin of error. SciFact claims rarely share exact words with their abstracts, which plays to meaning-based search. Hybrid is kept for everyday searches, where keywords matter: exact names, error messages, product codes and site names, which a meaning-only search can miss. The [personal-library evaluation](methodology.md#second-evaluation-your-own-library) measures those kinds of queries.

## Earlier pipeline

The numbers published before November 2026 came from the earlier pipeline: `all-MiniLM-L6-v2` embeddings, 300–500-word chunks (so most abstracts were a single chunk, and the second-chunk bonus rarely applied), and min-max score fusion (0.5 / 0.5).

| Method | MRR@10 | Recall@10 | nDCG@10 |
| --- | ---: | ---: | ---: |
| BM25 only | 0.648 | 0.812 | 0.678 |
| Vector only | 0.780 | 0.887 | 0.801 |
| Hybrid (min-max fusion) | 0.754 | 0.917 | 0.789 |

The current search beats it on every measure. Hybrid: MRR@10 0.786 against 0.754, Recall@10 0.922 against 0.917, nDCG@10 0.810 against 0.789. Vector-only: 0.812, 0.932 and 0.837.
