# Backend Architecture

The backend is a FastAPI application in `code/src/backend`.

## Modules

```text
backend/
├── main.py           API endpoints, rate limits, CORS, error handling
├── auth.py           Cognito access-token verification → user_id
├── accounts.py       Links Google and email sign-ins with the same verified email
├── library_moves.py  Moves pages saved before a sign-in was linked into its library
├── models.py         Pydantic request and response models
├── config.py         Settings from .env
├── ingest.py         ingest_page: the one way a page gets saved
├── cleaning.py       trafilatura extraction, junk-line removal, descriptions
├── url_utils.py      URL normalisation and page ids
├── youtube_utils.py  Video ids, metadata and transcripts
├── chunking.py       Sentence-aware overlapping chunks
├── embeddings.py     Sentence Transformers model, passage and query embeddings
├── retrieval.py      Hybrid search: BM25 + KNN, RRF, grouping, relevance floor
├── query_intent.py   Site words, time phrases and URLs in a query
├── rerank.py         Optional cross-encoder reranker
├── snippets.py       Query-focused snippets
├── summarizer.py     Gemini summaries
├── reports.py        Problem reports: SQLite store and background email sender
├── solr_client.py    Every Solr call, always scoped by user_id
├── page_filter.py    Server copy of the URL eligibility rules
└── cli.py            Command-line search
```

## Request flow

1. **Rate limiting** (slowapi): per user once authenticated, otherwise per IP. Limits range from 5/minute (delete all) to 120/minute (status checks, related pages).
2. **Authentication**: the `current_user_id` dependency verifies the bearer token and returns the library of its `sub` (Google and email sign-ins with the same verified email share one; see [Security](security.md)). Every endpoint except `/health` requires it.
3. **The endpoint** calls `ingest_page`, `hybrid_search` or the summariser with that user id.
4. **Solr** calls go through `SolrClient`, which adds the `user_id` filter to every query and rejects malformed ids.

## Saving pages

The API runs as one process (`uvicorn --workers 1`), and each user's saves run one at a time behind a per-user lock in `ingest.py`. Otherwise two saves of the same page could interleave (a shorter version's cleanup deleting a longer version's chunks), or two new pages could both pass the page limit. Solr shows new pages about a second after they're written, so new pages from the last few seconds are counted separately until it does.

## Start-up

The embedding model loads at start-up so the first save or search is fast, and two background threads start: the problem-report sender and the library mover (`library_moves.py`). The API refuses to start if the Cognito settings are missing.

## Caches

| Cache | Scope | Cleared when |
| --- | --- | --- |
| Query embeddings | last 1,024 queries | process restart |
| Sentence embeddings for snippets | LRU of 4,096 sentences | process restart |

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/setup_solr.sh` / `.ps1` | Create the core and install the schema, with a smoke test |
| `scripts/add_description_field.sh` | Add the `description` field to an existing core |
| `scripts/add_page_embedding_field.sh` | Add the `page_embedding` field to an existing core |
| `scripts/backfill_page_vectors.py` | Give older pages a page vector (resumable) |
| `scripts/reindex.py` | Copy pages from another core under a user id |
