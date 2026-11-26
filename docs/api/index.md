# API Reference

The MemoryLane API is a FastAPI application. On the live site it is served under **`https://memorylane.site/api`**. Locally it runs at `http://localhost:8000` with no `/api` prefix.

## Authentication

Every endpoint except `GET /health` needs a Cognito access token:

```http
Authorization: Bearer <access token>
```

Missing, expired or invalid tokens get `401`. The user is always the token's subject, so no endpoint takes a user id. See [Security](../architecture/security.md).

## Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Public status of Solr, the embedding model and Gemini |
| `POST` | `/memory` | Save (or update) a page |
| `GET` | `/memory/status` | Is this URL saved? |
| `POST` | `/memory/existing` | Which of these pages are still saved? |
| `DELETE` | `/memory/{page_id}` | Delete a page |
| `GET` | `/memory/{page_id}/related` | Pages closest in meaning to this one |
| `GET` | `/memories` | Saved pages, newest first |
| `POST` | `/search` | Hybrid search |
| `POST` | `/summarize` | Gemini summary of one page |
| `DELETE` | `/me/data` | Delete all your pages |
| `POST` | `/reports` | Report a problem (emailed to the maintainer) |

Request and response models are in `backend/models.py`. FastAPI's interactive docs are at `/docs` when running locally.

See [Endpoints](endpoints.md) for details.

## Quick example

Save a page, then find it. `$TOKEN` is a Cognito access token. In the web app or the extension it is managed for you; for a script, get one through the same sign-in flow (see [Security](../architecture/security.md#authentication)).

```bash
API=https://memorylane.site/api

# Save a page (the extension sends the page's HTML too; plain text works)
curl -s -X POST "$API/memory" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"url": "https://example.org/caching", "title": "Caching at the edge",
       "content": "…at least 50 words of the page text…", "is_manual": true}'

# Search it by describing it
curl -s -X POST "$API/search" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query": "the article about caching i read today", "num_results": 5}'
```

The first call answers `{"status": "saved", "message": …, "page": {"id": …}}`, and the second returns the page among its `results`, with a snippet.

## Rate limits

Limits are per user (per IP address before sign-in); a request over the limit gets `429`.

| Endpoint | Limit |
| --- | --- |
| `GET /memory/status`, `POST /memory/existing`, `GET /memory/{id}/related` | 120/minute |
| `POST /memory`, `DELETE /memory/{id}`, `GET /memories`, `POST /search` | 60/minute |
| `POST /summarize` | 20/minute |
| `DELETE /me/data` | 5/minute |
| `POST /reports` | 5/hour |

## Errors

| Status | Meaning |
| --- | --- |
| `400` | Missing required input (e.g. empty query) |
| `401` | No valid access token |
| `403` | A new page past the account's page limit |
| `404` | Page not found, or not yours |
| `422` | Invalid input, or a page with fewer than 50 words |
| `429` | Rate limit exceeded |
| `502` / `503` | Gemini failed / is not configured (summaries only) |
| `503` | Cognito couldn't be reached to look up a sign-in seen for the first time |
