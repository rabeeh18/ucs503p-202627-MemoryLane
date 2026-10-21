# Security

MemoryLane is multi-user, so the main security property is **isolation**: nobody can read, search, summarise, map or delete another person's pages.

## Authentication

- Sign-in is handled by **Amazon Cognito** (Google, or email and password). MemoryLane never handles passwords.
- The web app and the extension use the **authorization-code flow with PKCE** and a public client (no client secret).
- Every API request except `GET /health` needs `Authorization: Bearer <access token>`.

## Token verification

`backend/auth.py` verifies each access token:

- **RS256 signature** against the user pool's JWKS (keys cached for an hour)
- `exp` (not expired)
- `iss` (this user pool)
- `token_use == "access"` (ID tokens are refused)
- `client_id` (this app client)

The user id is the token's `sub`. **No endpoint accepts a user id from the client.**

## Data isolation

- `SolrClient` adds `{!term f=user_id}<sub>` to every query, scan, KNN search and delete, and raises an error if the id is missing or malformed. Isolation doesn't depend on each endpoint remembering to filter.
- KNN searches use the filter as a **pre-filter**, so other users' vectors are never candidates.
- `page_id` includes the user id in its hash, so two users' copies of a page never collide.
- A request for someone else's page gets `404`, the same as a missing page, so page ids can't be probed.
- `tests/test_isolation.py` checks this with two users: search, summaries, deletes, status, library, export, delete-all, the map, map search, related pages and topic search, plus a check that every Solr request carries the user filter.

## Network

- Only **Caddy** (ports 80 and 443) is public. HTTP redirects to HTTPS, with HSTS.
- Solr is bound to `127.0.0.1`. The backend has no published port and is reachable only through Caddy.

## Browser

- The access token lives in memory only. The refresh token is in `localStorage`, so a reload stays signed in.
- Because a script on the page could read that refresh token, the app **never renders user-supplied HTML** (Svelte's `{@html}` is not used), and Caddy sends a strict **Content Security Policy**: scripts from the site only, connections only to the site and Cognito, no framing, no plugins.
- The extension stores its tokens in `chrome.storage.local`, which web pages can't read.

## Abuse limits

- Rate limits per user (or per IP before sign-in), from 5/minute for export and delete-all to 120/minute for light reads.
- Request size limits: URL 2,048 characters, title 500, text 500 KB, HTML 3 MB, query 500 characters.
- The backend never fetches a URL supplied by the client. YouTube requests are built from a validated video id.

## Secrets

`.env` (Cognito ids, Gemini key) and the extension's private signing key are kept out of git.
