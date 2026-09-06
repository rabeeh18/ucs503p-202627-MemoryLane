# Summarization

MemoryLane provides optional AI-powered summarization for search results.

## How it works

Summarization is separate from the core retrieval process.

```text
Search
  ↓
Retrieve webpage
  ↓
Request summary
  ↓
Gemini
  ↓
Display summary
```

The `/search` endpoint can request summaries, and the frontend can also request a summary for an individual result.

## Gemini

The summarization component uses the Gemini API when Gemini is configured and available.

The backend also exposes Gemini availability through the `/health` endpoint.

## Detail level

The summarization system can determine an appropriate level of detail from the query before generating the summary.

## Privacy consideration

Unlike local indexing and retrieval, Gemini-based summarization can send browsing content to an external service. Avoid enabling external summarization for content that should remain entirely local unless the privacy implications are acceptable.
