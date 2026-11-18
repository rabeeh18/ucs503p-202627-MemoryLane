# Testing

## Backend (pytest)

```bash
cd code/src
pytest tests/ -v
```

Install the test tools with `pip install -r requirements-dev.txt`. The tests need no running Solr, Cognito or Gemini (the test setup clears `GEMINI_API_KEY`, so they never call it). Solr is replaced by an in-memory fake or a mock, `test_auth.py` signs its own tokens with a throwaway RSA key, other API tests override the signed-in user, and embeddings are stubbed.

| File | Covers |
| --- | --- |
| `test_auth.py` | Token verification: signature, expiry, issuer, `token_use`, `client_id` |
| `test_accounts.py` | Linking Google and email sign-ins: verified emails only, Cognito outages, delete-all |
| `test_isolation.py` | Two users can never see, search, summarise or delete each other's pages, or get them as related pages |
| `test_api.py` | Endpoint contracts, status codes, Gemini-off behaviour |
| `test_ingest.py` | Save, unchanged, update without duplicate chunks, 422 on short pages |
| `test_cleaning.py` | trafilatura extraction, fallbacks, junk lines, descriptions |
| `test_chunking.py` | Chunk sizes, overlap, short tails, long sentences |
| `test_url_normalization.py` | URL normalisation and page ids |
| `test_retrieval.py` | RRF, page grouping, the relevance floor |
| `test_query_intent.py` | Site words, time phrases and URLs in queries |
| `test_page_filter.py` | The server's copy of the auto-capture rules (email, private apps, local addresses, secret links, `noindex`), and the API refusing unsafe automatic saves while still allowing manual ones |
| `test_audit_fixes.py` | Fixes from the November 2026 bug audit: one save at a time per user, the page limit before Solr shows new pages, exact URLs keeping their case, BM25-only and vector-only runs, YouTube `/live/` links, moving pages after sign-ins link, and re-checking changed emails |
| `test_rerank.py` | Optional cross-encoder reranking |
| `test_snippets.py` | Snippet sentence choice, length and fallbacks |
| `test_solr_client.py` | Every Solr query carries the user filter; commit behaviour; escaping |
| `test_youtube.py` | Video ids, transcripts sent by the extension or fetched by the server, the description fallback, the two-hour auto-capture limit |
| `test_reports.py` | Problem reports: storage, the email contents, retries and backoff, the rate limit |
| `test_evaluation.py` | The generated-query evaluation: metrics, URL matching, per-user scoring, comparisons |
| `test_reindex.py`, `test_backfill.py` | The re-index and page-vector backfill scripts |

## Web app (vitest)

```bash
cd code/src/frontend
npm test          # vitest
npm run check     # svelte-check (types and Svelte diagnostics)
```

Unit tests cover the pure modules in `src/lib/`: delete-with-undo, including pages saved again after a delete (`deletes.test.js`), domain letters (`domain.test.js`), home-page greetings (`greetings.test.js`), problem reports (`report.test.js`), the extension's YouTube fetch (`extensionYoutube.test.js`) and auto-capture rules, both addresses and what's on the page (`extensionFilter.test.js`), and the docs site's meaning-based search (`docsSearch.test.js`).

## Continuous integration

`.github/workflows/ci.yml` runs the backend tests and the frontend tests and checks on every push and pull request. `.github/workflows/mkdocs.yml` builds this documentation with `mkdocs build --strict` on every push that changes it, so broken links or config fail the check. It doesn't publish: the site is published by hand from the repository root with `mkdocs gh-deploy --strict`, which builds it and pushes it to the `gh-pages` branch.

## Retrieval quality

Retrieval quality is measured separately, with the [SciFact evaluation](../evaluation/methodology.md), because it needs a real Solr core and the embedding model.

## Manual check

1. `GET /health` → all `true`
2. Save a page from the extension → it appears under **Recently saved**
3. Save it again → `unchanged`, same chunk count
4. Search with different wording from the page → it's found, with a sensible snippet
5. **Summarise** → a summary (with a Gemini key)
6. Sign in as a second user → none of the first user's pages are visible
