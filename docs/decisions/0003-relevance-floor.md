# 0003. Drop weak matches with a relevance floor

**Status:** Accepted · **Date:** October 2026, revised November 2026

## Context

KNN always returns its 50 nearest chunks, however unrelated, and RRF ranks whatever it's given. So a small library always produced a full list of results, even when only one page was relevant. Users read that as "search is broken".

BM25 has a similar problem: it matches a page that shares *any one* word with the query. Searching "greatest football player of all time" returned the Lionel Messi page, but also Nintendo ("the greatest games of all time") and Video game ("the player ... a later time").

## Decision

After grouping chunks into pages:

1. A page with **no** BM25 match needs a best-chunk cosine similarity of at least `MIN_VECTOR_SIMILARITY` (0.55).
2. *(November 2026)* A keyword match that holds fewer than `KEYWORD_FULL_MATCH` (75%) of the query's words needs that same similarity. If it holds most of them, it's kept whatever its similarity, so exact names and error codes are never lost. When a page's similarity isn't known, one extra KNN request restricted to those pages looks it up.

The thresholds were checked on real pages with `bge-small-en-v1.5`. Messi's best chunk scores 0.69; Nintendo 0.51 and Video game 0.46 are dropped.

## Alternatives

| Option | Why not |
| --- | --- |
| Always show the top 10 | The original behaviour: confident-looking junk |
| A cut-off on the fused RRF score | RRF scores depend on list lengths and ranks, not on relevance, so no threshold means the same thing twice |
| A cross-encoder reranker | Better judgement, but too much memory for the live server ([0004](0004-one-ec2-instance.md)); it stays available behind a flag |

## Consequences

- **Easier:** a short list now means "nothing else was close", which the UI says.
- **Harder:** a fixed threshold suits one embedding model. Changing models means re-checking 0.55. A genuinely relevant page with unusual wording can fall just under it.
- Keyword checks cost one extra KNN request only when a partial keyword match has no similarity yet (at most 50 pages).
