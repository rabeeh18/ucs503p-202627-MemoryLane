# Week 5: Moving to Apache Solr

*24 – 30 Aug 2026*

## What I did

Added hybrid search (keywords plus meaning) and then moved the whole store from ChromaDB to Apache Solr. Rewrote chunking, the CLI and the backend around a Solr client, and removed the outdated documentation.

## Problem

With ChromaDB for vectors, keyword search needed a second system, and the two had to be kept in sync. Exact words (names, error codes) were often missed by vector search alone.

## Fix

Solr 9 does both: BM25 keyword search and dense-vector (KNN) search in one core, with the same filters. One store meant one source of truth. This later became ADR 0001.

## Learned

Choosing the storage engine is the decision that is hardest to undo, so it is worth changing early. The migration touched 67 files; a month later it would have touched far more.
