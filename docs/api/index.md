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
| `DELETE` | `/memory/{page_id}` | Delete a page |
| `GET` | `/memory/{page_id}/related` | Pages closest in meaning to this one |
| `GET` | `/memories` | Saved pages, newest first |
| `POST` | `/search` | Hybrid search, optionally within a map topic |
| `POST` | `/summarize` | Gemini summary of one page |
| `GET` | `/map` | The library map |
| `GET` | `/map/search` | Find topics and pages on the map |
| `GET` | `/me/export` | Download all your pages as JSON |
| `DELETE` | `/me/data` | Delete all your pages |

Request and response models are in `backend/models.py`. FastAPI's interactive docs are at `/docs` when running locally.

See [Endpoints](endpoints.md) for details.

## Errors

| Status | Meaning |
| --- | --- |
| `400` | Missing required input (e.g. empty query) |
| `401` | No valid access token |
| `404` | Page not found, or not yours |
| `409` | Topic search on a map that has since changed |
| `422` | Invalid input, or a page with fewer than 50 words |
| `429` | Rate limit exceeded |
| `502` / `503` | Gemini failed / is not configured (summaries only) |
