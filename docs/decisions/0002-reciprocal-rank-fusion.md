# 0002. Fuse rankings with Reciprocal Rank Fusion

**Status:** Accepted · **Date:** October 2026 · Replaces min-max score fusion

## Context

Hybrid search gets two ranked lists: BM25 and KNN. Their scores are on different scales. BM25 scores are unbounded and depend on the query, while cosine similarities sit between 0 and 1. They have to be combined into one ranking.

The first version min-max normalised each list to 0–1 and averaged them (0.5 / 0.5). On the SciFact benchmark that hybrid had the best recall, but a *lower* MRR than vector search alone ([Results](../evaluation/results.md)): mixing in BM25 sometimes pushed the first relevant result down. Min-max also depends on the highest and lowest score in each list, so one outlier shifts every other score.

## Decision

Fuse **ranks** with Reciprocal Rank Fusion: a chunk scores \(\sum_i w_i / (k + r_i)\) over the lists it appears in, with \(k = 60\) and both weights 1.0. Later, the site and time lists (see [Retrieval](../architecture/retrieval.md#site-time-and-url-in-the-query)) joined the same sum.

## Alternatives

| Option | Why not |
| --- | --- |
| Keep min-max averaging | Sensitive to outliers, and measured worse at putting the right page first |
| Z-score normalisation | Still compares scores that mean different things, and is unstable on short lists |
| A learned fusion model | Needs labelled training data that doesn't exist for personal libraries |

## Consequences

- **Easier:** no score calibration, and adding another ranked list is one more term. A chunk found by both retrievers rises naturally.
- **Harder:** RRF throws away *how much* better one result is than the next. It also gives every list's top result real weight, even when that list's matches are all poor, which is part of why [0003](0003-relevance-floor.md) was needed.
- The current pipeline hasn't been re-benchmarked on SciFact since this change; the Results page says so.
