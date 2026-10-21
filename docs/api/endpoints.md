# API Endpoints

Paths are relative to the API base (`https://memorylane.site/api` on the live site). All endpoints except `/health` need a bearer token. The rate limit is per user.

## `GET /health`

Public. Reports whether the backend's dependencies are ready.

```json
{ "status": "ok", "solr": true, "embedding_model": true, "gemini": true }
```

`status` is `ok` when Solr and the embedding model are ready. `gemini: false` only means summaries are off.

---

## `POST /memory`

Save a page, or update it if it's already saved. Rate limit: 60/minute.

```json
{
  "url": "https://example.com/article",
  "title": "Example Article",
  "content": "Visible text of the page...",
  "html": "<!doctype html>...",
  "canonical_url": "https://example.com/article",
  "is_manual": true
}
```

`html` and `canonical_url` are optional. When `html` is present, the main text is extracted from it; `content` is the fallback.

```json
{
  "status": "saved",
  "message": "Memory stored successfully",
  "page": {
    "id": "3f9c...", "url": "https://example.com/article", "title": "Example Article",
    "domain": "example.com", "timestamp": "2026-10-22T09:30:00Z", "chunks": 4
  }
}
```

`status` is `saved`, `unchanged` (same text as before) or `skipped` (e.g. a YouTube video that can't be saved). A page with fewer than 50 words gets `422`.

---

## `GET /memory/status?url=...&canonical_url=...`

Whether you've saved this URL, normalised the same way as a save. Rate limit: 120/minute.

```json
{ "saved": true, "page": { "id": "3f9c...", "url": "...", "title": "...", "domain": "...", "timestamp": "..." } }
```

---

## `DELETE /memory/{page_id}`

Delete one of your pages. Returns `204`, or `404` if it isn't yours. Rate limit: 60/minute.

---

## `GET /memory/{page_id}/related?k=5`

Your other pages closest in meaning to this one (`k` from 1 to 20). Rate limit: 120/minute.

```json
{
  "page_id": "3f9c...",
  "related": [
    { "id": "a1b2...", "title": "...", "url": "...", "domain": "...", "saved_at": "...", "similarity": 0.81 }
  ]
}
```

---

## `GET /memories?limit=20&offset=0`

Your pages, newest first (`limit` up to 100). Rate limit: 60/minute.

```json
{ "total": 278, "pages": [ { "id": "...", "url": "...", "title": "...", "domain": "...", "timestamp": "...", "chunks": 3 } ] }
```

---

## `POST /search`

Hybrid search over your pages. Rate limit: 60/minute.

```json
{
  "query": "documentation about ROS navigation",
  "num_results": 10,
  "summarize": false,
  "debug": false,
  "topic": null
}
```

| Field | Notes |
| --- | --- |
| `query` | Required, up to 500 characters |
| `num_results` | 1–20, default 10 |
| `summarize` | Also summarise each result with Gemini (slow; the web app uses `/summarize` per result instead) |
| `debug` | Add ranks, scores and timings |
| `topic` | A topic id from `GET /map`: search only that topic's pages. `409` if the map has changed |

```json
{
  "query": "documentation about ROS navigation",
  "results": [
    {
      "rank": 1, "id": "3f9c...", "title": "Nav2 Documentation", "url": "...",
      "domain": "docs.nav2.org", "timestamp": "...",
      "snippet": "Nav2 is the professionally supported successor of the ROS Navigation Stack...",
      "summary": null
    }
  ]
}
```

With `debug: true`, each result also has `bm25_rank`, `knn_rank`, `fused_score`, `rerank_score` and `vector_similarity`, and the response has `timings` in milliseconds.

---

## `POST /summarize`

Summarise one of your pages with Gemini. Rate limit: 20/minute.

```json
{ "query": "brief overview", "id": "3f9c..." }
```

```json
{ "id": "3f9c...", "summary": "..." }
```

`404` if the page isn't yours, `503` if Gemini isn't configured, `502` if it failed.

---

## `GET /map`

Your library map. Rate limit: 30/minute.

```json
{
  "status": "ok",
  "version": "9b1e4c",
  "topics": [ { "id": "9b1e4c-3", "label": "Protein Folding", "count": 31, "x": 0.42, "y": 0.38, "rx": 0.09, "ry": 0.065 } ],
  "pages": [ { "id": "3f9c...", "title": "...", "url": "...", "domain": "...", "saved_at": "...", "x": 0.44, "y": 0.36, "topic": "9b1e4c-3" } ],
  "edges": [ { "a": "3f9c...", "b": "a1b2...", "kind": "intra" } ],
  "topic_links": [ { "a": "9b1e4c-3", "b": "9b1e4c-7" } ],
  "counts": { "pages": 278, "topics": 9, "unclustered": 12, "without_vectors": 0 }
}
```

Coordinates are in a 0–1 box. A page with `topic: null` is unclustered. With fewer than 10 pages the response is `{ "status": "too_few", "count": 6, ... }`.

---

## `GET /map/search?q=...`

Find topics on your map by name and by the pages inside them. Rate limit: 120/minute.

```json
{ "query": "proteins", "version": "9b1e4c", "topics": [ { "id": "9b1e4c-3", "label": "Protein Folding", "score": 0.74 } ], "pages": ["3f9c...", "..."] }
```

---

## `GET /me/export`

Downloads `memorylane-export.json` with every page you saved (URL, title, timestamp and full text), newest first. Rate limit: 5/minute.

---

## `DELETE /me/data`

Deletes all your pages. Returns `204`. Rate limit: 5/minute.
