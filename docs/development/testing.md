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

## Local engine parity

The browser engine (`extension/engine/`) must rank exactly as the server. `code/src/evaluation/parity/` compares them against a throwaway Solr (with the extension's `npm ci --ignore-scripts && npm run vendor` done first):

```bash
docker run -d --name ml-parity-solr -p 127.0.0.1:8984:8983 solr:9.7
docker exec ml-parity-solr solr create -c parity -d _default
SOLR_PORT=8984 CORE_NAME=parity ./scripts/setup_solr.sh
python -m evaluation.parity.solr_corpus --solr http://localhost:8984/solr/parity --out /tmp/chunks.json
node evaluation/parity/bm25_check.mjs /tmp/chunks.json           # keyword search: 119/119 identical
python -m evaluation.parity.server_results --solr http://localhost:8984/solr/parity --out /tmp/server.json
node evaluation/parity/hybrid_check.mjs /tmp/chunks.json /tmp/server.json   # full search: 117/117
python -m evaluation.parity.ingest_reference <pages dir> /tmp/cases.json
node evaluation/parity/ingest_check.mjs /tmp/cases.json         # saving: identical chunks
node evaluation/parity/engine_check.mjs <pages dir>             # store, reopen, move, delete
```

`tests/test_extension_settings.py` keeps the extension's default search settings equal to `backend/config.py`.

## Manual check

1. `GET /health` → all `true`
2. Save a page from the extension → it appears under **Recently saved**
3. Save it again → `unchanged`, same chunk count
4. Search with different wording from the page → it's found, with a sensible snippet
5. **Summarise** → a summary (with a Gemini key)
6. Sign in as a second user → none of the first user's pages are visible
7. With the extension's storage on **this device** (the default): save a page → the popup says *on this device*; it is found on memorylane.site in that browser, marked *on this device* in the library, and not on the server (`/memories`)
8. Settings → **Move pages here to the server** → the page is now *on the server* and still found; **Bring server pages to this device** moves it back
9. Set the size limit below the device's usage with **Ask before moving pages** → the popup asks; **Move oldest pages** moves them
10. **Back up now** → a recovery key is shown; delete the page, **Restore from backup** with the key → it's back
11. Sign out of the extension → memorylane.site no longer shows device pages; sign in → they're back
