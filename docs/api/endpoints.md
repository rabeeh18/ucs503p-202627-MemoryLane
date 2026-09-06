# API Endpoints

## `GET /health`

Checks the availability of the main backend dependencies.

The response reports:

```json
{
  "status": "ok",
  "solr": true,
  "embedding_model": true,
  "gemini": true
}
```

`gemini` may be false when optional Gemini functionality is not configured or available.

---

## `POST /memory`

Stores a webpage as a MemoryLane memory.

### Request

```json
{
  "url": "https://example.com/article",
  "title": "Example Article",
  "content": "Article content...",
  "canonical_url": "https://example.com/article",
  "is_manual": false
}
```

### Processing

The backend validates the URL, normalizes it, creates a webpage identifier, handles supported YouTube URLs, chunks the content, generates embeddings, and indexes the resulting chunks in Solr.

### Response

The response contains:

- `success`
- `message`
- `metadata`

The metadata includes the URL, title, generated ID, chunk count, and timestamp.

---

## `POST /search`

Searches stored memories.

### Request

```json
{
  "query": "documentation about ROS navigation",
  "num_results": 5,
  "summarize": false,
  "debug": false
}
```

`num_results` accepts values from 1 to 20.

### Response

A search response contains the original query and a list of webpage-level results.

Each result includes:

- rank
- ID
- title
- URL
- domain
- timestamp
- optional summary

The `debug` option can expose retrieval scores for development and analysis.

---

## `POST /summarize`

Requests a summary for a selected memory.

### Request

```json
{
  "query": "What are the main ideas?",
  "id": "memory-id"
}
```

### Response

```json
{
  "id": "memory-id",
  "summary": "..."
}
```

The summarization path uses Gemini when the service is available.
