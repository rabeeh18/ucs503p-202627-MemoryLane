# Week 5: Hybrid Search and Version 2

*24 – 30 Aug 2026*

## What I did

Wrote a hybrid retrieval module that combines keyword search (BM25) with the ChromaDB vector search, using Reciprocal Rank Fusion, and kept it in one module so the backend and the evaluation script ran exactly the same code. I also cleared out files the prototype no longer needed: a large exported database viewer, the old query script, a manual test script and the Tampermonkey userscript. At the lab on 24 Aug, Sir walked us through Apache Solr: built-in keyword and vector search in one engine, fast indexed retrieval, and a simpler pipeline without our separate reranker and cutoff. He also advised us to keep evidence of each version (screenshots, videos, code) to show later why our choices worked. By the end of the week the team had moved search to Solr, and I wrote the Version 2 update on the forum: why the retrieval stack moved to Solr, the new Svelte frontend, and summaries generated only when the user clicks "Summarise".

## Problem

Ordinary word splitting broke technical terms apart: "C++", "React.js", "gpt-4" and "useEffect" became fragments that matched the wrong pages. And BM25 scores and cosine similarities sit on different scales, so adding them together needed careful calibration.

## Fix

The tokenizer keeps `.`, `+`, `#`, `_` and `-` inside a token, so technical names survive as single words, and it strips only a sentence-ending full stop. Titles are repeated ahead of the body as a simple boost. The two result lists are fused by rank, not by score, so no calibration is needed.

## Learned

Fusing by rank is simple and robust, which is why it stayed when search moved to Solr. Writing the Version 2 update also meant explaining the old design's limits (separate keyword and vector systems, a reranker, a terminal-only interface), which made the reasons for the new one clear. Following Sir's advice, the update included evidence from the old version: the data stored in ChromaDB and the terminal output of a query.

## Forum

- [Learnings from lab (24/8/26)](https://tiet-ucs503.bvraghav.com/d/55-learnings-from-lab-24826--memorylane-/1) (24–30 Aug): the points discussed with Sir about Solr and the next steps, posted by Rabeeh
- [Version 2 Update](https://tiet-ucs503.bvraghav.com/d/58-version-2-update-memorylane/1) (30 Aug): my write-up of the move to Solr, the new frontend and on-demand summaries
