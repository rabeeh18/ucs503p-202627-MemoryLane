# Week 5: Moving to Apache Solr

*24 – 30 Aug 2026*

## What I did

At the 24 Aug lab we discussed Apache Solr: one engine with built-in BM25 and vector search, which could replace ChromaDB plus our separate BM25 setup. We also discussed search breadth and depth, and dropping the reranker and the adaptive cutoff. The plan was to move to Solr, make the easy improvements first, and build a basic Svelte frontend by the end of the week. By 30 Aug we had:

- added hybrid search and moved the whole store to Solr (67 files changed);
- run Solr in Docker;
- tested the FastAPI `/search` and `/summarize` endpoints in Swagger;
- built a basic Svelte frontend with a **Summarise** button;
- replaced the TamperMonkey userscript with our own Chrome extension.

## Problem

The old design was terminal-only and had too many moving parts: a TamperMonkey script, ChromaDB for vectors, a separate BM25 step and a reranker, all of which had to be kept in sync.

## Fix

Solr 9 does both BM25 keyword search and dense-vector (KNN) search in one index, with the same filters, so one store became the single source of truth. This later became ADR 0001. The FastAPI backend, the Svelte frontend and our own extension replaced the terminal and the userscript. I then proposed the next features on the forum: automatic capture with a manual/automatic toggle, filtering out sensitive pages (logins, banking, social media), treating URL variants as one page, and YouTube support.

## Learned

Choosing the storage engine is the hardest decision to undo, so it is worth changing early. Acting on the lab discussion in week 5 cost one migration; a month later it would have cost far more.

## Forum

- [Learnings from lab (24/8/26)](https://tiet-ucs503.bvraghav.com/d/55-learnings-from-lab-24826--memorylane-/1) (24 Aug): notes from the lab on Solr and the plan for the week; [follow-up](https://tiet-ucs503.bvraghav.com/d/55-learnings-from-lab-24826--memorylane-/3) when it was done (30 Aug)
- [Version 2 Update](https://tiet-ucs503.bvraghav.com/d/58-version-2-update-memorylane/1) (30 Aug): the new design, and the [proposed next features](https://tiet-ucs503.bvraghav.com/d/58-version-2-update-memorylane/5)
