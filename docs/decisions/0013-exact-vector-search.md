# 0013. Score vectors exactly instead of with HNSW

**Status:** Accepted · **Date:** November 2026 · Changes the vector search of [0001](0001-solr.md)

## Context

Solr's `{!knn}` query walks an HNSW graph: fast, but approximate. Comparing it with an exact scan over the same SciFact chunks, it **missed at least one true top-50 neighbour in 71 of 100 queries** (usually around rank 35 to 50).

The local engine ([0012](0012-local-first-storage.md)) scans every vector exactly. HNSW's misses depend on how Lucene built its graph and merged segments, so the browser can't reproduce them, and with approximate search on the server the two engines disagreed on 27 of 117 parity queries.

## Decision

The server scores vectors **exactly**: a function query, `{!func}vectorSimilarity(FLOAT32,COSINE,embedding,[...])`, scores every chunk the filters allow with the same `(1 + cos) / 2` score `{!knn}` gives, and Solr returns the best k (`backend/solr_client.py`, `knn_search` and `related_pages`).

## Alternatives

| Option | Why not |
| --- | --- |
| Keep HNSW and accept differences | Local and server would rank the same pages differently |
| Ask HNSW for more neighbours (topK 4k) and cut | Fewer misses, never none |
| Imitate HNSW in the browser | Its misses depend on Lucene's graph and segment merges |

## Consequences

- **Easier:** both engines return the same pages: 117 of 117 parity queries match in pages, order and snippets. Search is also slightly more accurate: it no longer misses neighbours.
- **Cost:** on the parity core (1,761 chunks) the exact query took 7 ms median against 5 ms, and its slowest call was 23 ms (HNSW's was 2.1 s, a cold start). It grows linearly with a user's chunks; at the 5,000-page cap (about 50,000 chunks) it is still tens of milliseconds, because every query is already filtered to one user.
- The SciFact results were measured again with exact search ([Results](../evaluation/results.md)).
