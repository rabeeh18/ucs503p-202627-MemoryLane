# System Overview

MemoryLane is two pipelines that meet in Solr: one that saves pages and one that finds them. Both run under the signed-in user's id.

## Saving a page

```text
Page in Chrome (or a YouTube video)
          ↓
Extension: HTML + text + canonical URL
          ↓
Caddy (HTTPS) → FastAPI, with a Cognito access token
          ↓
Verify the token → user_id
          ↓
Normalise the URL → page_id = hash(user_id, URL)
          ↓
Clean (trafilatura) or fetch the transcript
          ↓
At least 50 words? Changed since last save?
          ↓
Chunk (≤150 words, 30-word overlap)
          ↓
Embed "title + chunk" (bge-small-en-v1.5, 384-d)
          ↓
Solr: chunks + page vector + description
```

## Finding it

```text
Query (typed or spoken)
          ↓
Web app → Caddy → FastAPI (token → user_id)
          ↓
   ┌──────────────┬──────────────┐
BM25 (edismax)        Vector KNN (query embedding)
   └──────────────┴──────────────┘
          ↓   both filtered by user_id
Reciprocal Rank Fusion
          ↓
(optional cross-encoder rerank)
          ↓
Group chunks into pages
          ↓
Relevance floor
          ↓
Snippets → results
```

## Mapping the library

```text
User's page vectors (newest 2,000)
          ↓
PCA → k-means (k chosen by silhouette) → split oversized topics
          ↓
Outliers left unclustered
          ↓
Topic names (Gemini, or keywords)
          ↓
Layout + links → cached per user
```

## Separation of responsibilities

| Part | Responsibility |
| --- | --- |
| Extension | Collecting pages, auto-capture rules, excluded sites |
| Web app | Search, library, map, summaries, account |
| Cognito | Who the user is |
| Caddy | HTTPS, static files, routing `/api` |
| FastAPI | Token checks, ingest, retrieval, map, summaries |
| Sentence Transformers | Embeddings |
| Solr | Storage, BM25 and KNN search |
| Gemini | Optional summaries and topic names |
