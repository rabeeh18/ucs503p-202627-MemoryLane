# 0014. Own BM25 and a plain vector scan in the browser, not Orama

**Status:** Accepted · **Date:** November 2026

## Context

Local search ([0012](0012-local-first-storage.md)) needs keyword (BM25) search and vector search in the browser. Orama is a popular JavaScript search library with both. The team compared it with a small purpose-built engine on the same corpus (24,250 chunks) and model:

| Part | Option | Latency | nDCG@10 | Memory (start, steady) |
| --- | --- | --- | --- | --- |
| Keyword search (BM25 only) | Own BM25 | 26 ms | 0.682 | 30 MB, 28 MB |
| | Orama BM25 | 56 ms | 0.559 | 478 MB, 287 MB |
| Vector store | Orama (float32) | 33 ms | 0.742 | 192 MB, 98 MB |
| | No Orama (int8 scan) | 26 ms | 0.740 | 30 MB, 28 MB |
| Vector precision | fp32 | 25 ms | 0.742 | 56 MB, 54 MB |
| | fp16 | 32 ms | 0.742 | 39 MB, 37 MB |
| | q8 (int8) | 26 ms | 0.740 | 30 MB, 28 MB |

## Decision

No Orama. `extension/engine/bm25.js` implements Solr's scoring exactly: the same `text_en` analysis (`analyzer.js`, with Lucene's Porter stemmer in `porter.js`), edismax over `title^2 text` with phrase boosts `text^2 title^3`, and Lucene 9's BM25 (k1 1.2, b 0.75) with its one-byte document lengths and float arithmetic. Vectors are held as **int8** in memory for the scan, and the best candidates are **rescored with the full vectors** read from the store, so final scores are exact (`local_index.js`).

The model runs at full precision (fp32): its vectors match the server's to about 1e-7 (q8 weights moved cosines by ~0.004, enough to tip pages across the 0.55 relevance floor).

## Alternatives

| Option | Why not |
| --- | --- |
| Orama | Twice as slow, lower nDCG for BM25, about 10x the memory (table above) |
| fp32 vectors in memory | Twice the memory of int8 for the same ranking once rescored |
| q8 model weights | Smaller download, but cosines differ from the server's enough to change the floor's decisions |

## Consequences

- **Easier:** about 30 MB of memory for a large library, and results identical to the server's: on SciFact, 2,006 texts analyse identically to Solr and 119 of 119 keyword queries return the same top 50 with the same scores.
- **Harder:** the engine is MemoryLane's own code to maintain. Changes to the server's search (`backend/retrieval.py`, Solr settings) must be mirrored, and the parity checks (`code/src/evaluation/parity/`) show any drift.
