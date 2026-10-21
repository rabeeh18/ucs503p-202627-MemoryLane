# Testing

## Backend (pytest)

```bash
cd code/src
pytest tests/ -v
```

The tests need no running Solr, Cognito or Gemini. Solr is replaced by an in-memory fake or a mock, `test_auth.py` signs its own tokens with a throwaway RSA key, other API tests override the signed-in user, and embeddings are stubbed.

| File | Covers |
| --- | --- |
| `test_auth.py` | Token verification: signature, expiry, issuer, `token_use`, `client_id` |
| `test_isolation.py` | Two users can never see, search, summarise, map or delete each other's pages |
| `test_api.py` | Endpoint contracts, status codes, Gemini-off behaviour |
| `test_ingest.py` | Save, unchanged, update without duplicate chunks, 422 on short pages |
| `test_cleaning.py` | trafilatura extraction, fallbacks, junk lines, descriptions |
| `test_chunking.py` | Chunk sizes, overlap, short tails, long sentences |
| `test_url_normalization.py` | URL normalisation and page ids |
| `test_retrieval.py` | RRF, page grouping, the relevance floor |
| `test_rerank.py` | Optional cross-encoder reranking |
| `test_snippets.py` | Snippet sentence choice, length and fallbacks |
| `test_solr_client.py` | Every Solr query carries the user filter; commit behaviour; escaping |
| `test_youtube.py` | Video ids, transcripts, the two-hour auto-capture limit |
| `test_library_map.py` | Number of topics, splits, outliers, labels, layout, links |
| `test_map_api.py` | `/map`, `/map/search`, related pages, topic search and `409` |
| `test_reindex.py`, `test_backfill.py` | The re-index and page-vector backfill scripts |

## Web app (vitest)

```bash
cd code/src/frontend
npm test          # vitest
npm run check     # svelte-check (types and Svelte diagnostics)
```

Unit tests cover the pure modules in `src/lib/`: map geometry and state (`mapView.test.js`), delete-with-undo (`deletes.test.js`) and domain letters (`domain.test.js`).

## Retrieval quality

Retrieval quality is measured separately, with the [SciFact evaluation](../evaluation/methodology.md), because it needs a real Solr core and the embedding model.

## Manual check

1. `GET /health` → all `true`
2. Save a page from the extension → it appears under **Recently saved**
3. Save it again → `unchanged`, same chunk count
4. Search with different wording from the page → it's found, with a sensible snippet
5. **Summarise** → a summary (with a Gemini key)
6. Open **Map** with 10+ pages → named topics; click a page → related pages
7. Sign in as a second user → none of the first user's pages are visible
