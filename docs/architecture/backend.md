# Backend Architecture

The backend is a FastAPI application in `code/src/backend`.

## Modules

```text
backend/
├── main.py           API endpoints, rate limits, CORS, error handling
├── auth.py           Cognito access-token verification → user_id
├── models.py         Pydantic request and response models
├── config.py         Settings from .env
├── ingest.py         ingest_page: the one way a page gets saved
├── cleaning.py       trafilatura extraction, junk-line removal, descriptions
├── url_utils.py      URL normalisation and page ids
├── youtube_utils.py  Video ids, metadata and transcripts
├── chunking.py       Sentence-aware overlapping chunks
├── embeddings.py     Sentence Transformers model, passage and query embeddings
├── retrieval.py      Hybrid search: BM25 + KNN, RRF, grouping, relevance floor
├── rerank.py         Optional cross-encoder reranker
├── snippets.py       Query-focused snippets
├── library_map.py    Topics, labels, layout, links, per-user map cache
├── summarizer.py     Gemini summaries and topic names
├── solr_client.py    Every Solr call, always scoped by user_id
├── page_filter.py    Server copy of the URL eligibility rules
└── cli.py            Command-line search
```

## Request flow

1. **Rate limiting** (slowapi): per user once authenticated, otherwise per IP. Limits range from 5/minute (export, delete all) to 120/minute (status checks, related pages, map search).
2. **Authentication**: the `current_user_id` dependency verifies the bearer token and returns its `sub`. Every endpoint except `/health` requires it.
3. **The endpoint** calls `ingest_page`, `hybrid_search`, `map_service` or the summariser with that user id.
4. **Solr** calls go through `SolrClient`, which adds the `user_id` filter to every query and rejects malformed ids.

## Start-up

The embedding model loads at start-up so the first save or search is fast. The API refuses to start if the Cognito settings are missing.

## Caches

| Cache | Scope | Cleared when |
| --- | --- | --- |
| Query embeddings | last 1,024 queries | process restart |
| Sentence embeddings for snippets | LRU of 4,096 sentences | process restart |
| Library map | per user, 50 users, 10-minute TTL | the user saves or deletes a page |
| Topic labels | per topic membership | process restart |

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/setup_solr.sh` / `.ps1` | Create the core and install the schema, with a smoke test |
| `scripts/add_description_field.sh` | Add the `description` field to an existing core |
| `scripts/add_page_embedding_field.sh` | Add the `page_embedding` field to an existing core |
| `scripts/backfill_page_vectors.py` | Give older pages a page vector (resumable) |
| `scripts/reindex.py` | Copy pages from another core under a user id |
