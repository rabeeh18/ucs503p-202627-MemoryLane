# System Architecture

```text
┌──────────────────┐   ┌──────────────────┐        ┌──────────────────┐
│ Chrome extension │   │  Svelte web app  │◀──────▶│  Amazon Cognito  │
│ save, auto-save  │   │ search, map, lib │  PKCE  │ Google / email   │
└────────┬─────────┘   └────────┬─────────┘        └──────────────────┘
         │  HTTPS + Bearer access token
         ▼                      ▼
┌─────────────────────────────────────────┐
│ Caddy: TLS, static web app, /api proxy  │
└────────────────────┬────────────────────┘
                     ▼
┌─────────────────────────────────────────┐        ┌──────────────────┐
│ FastAPI backend                         │───────▶│ Gemini           │
│ token check → user_id                   │        │ (optional)       │
│ ingest · retrieval · map · summaries    │        └──────────────────┘
│ Sentence Transformers (bge-small)       │
└────────────────────┬────────────────────┘
                     ▼   always filtered by user_id
┌─────────────────────────────────────────┐
│ Apache Solr 9.7 · core memorylane_v2    │
│ BM25 (text_en) + HNSW vectors           │
└─────────────────────────────────────────┘
```

All three server pieces run with Docker Compose on one EC2 instance. Only Caddy is reachable from the internet.

## Components

### Chrome extension

The collection layer. It saves the current page on request, runs optional auto-capture with its eligibility rules and excluded sites, and signs in with Cognito through `chrome.identity`. It doesn't search; searching happens on the website.

### Svelte web app

The search interface: home with recent pages, results with snippets and summaries, the library, the library map, the extension page, privacy and the account menu. It is built into static files that Caddy serves.

### Amazon Cognito

Hosts sign-in (Google, or email and password) and issues access tokens. The web app and extension both use the authorization-code flow with PKCE and a public client.

### Caddy

Gets and renews HTTPS certificates, serves the web app with a strict Content Security Policy, serves the extension zip, proxies `/api/*` to the backend, and redirects `www.memorylane.site` to `memorylane.site`.

### FastAPI backend

The application layer. It verifies every request's token, then saves pages, searches, builds library maps, finds related pages and asks Gemini for summaries, all scoped to the token's user. It loads the embedding model once at start-up.

### Apache Solr

Stores chunks, page vectors and metadata, and runs BM25 and KNN search. It is bound to localhost on the server.

### Gemini

Optional. Summarises a single page on request, and names library-map topics. Without a key, both fall back gracefully.

## Design principles

- **The server owns identity.** User ids come only from verified tokens.
- **One ingest path.** The API, scripts and evaluation all save pages through `ingest_page`, so they behave identically.
- **Search is page-level.** Retrieval works on chunks, but users see pages.
- **Optional parts stay optional.** Gemini and the reranker can be off without breaking search.
