# System Overview

MemoryLane is organized as a pipeline connecting the browser, frontend, backend, content-processing layer, search index, and retrieval system.

## Memory ingestion

```text
Browser Page / YouTube Video
          ↓
    Browser Extension
          ↓
     Capture / Filter
          ↓
        FastAPI
          ↓
    URL Normalization
          ↓
   Content Processing
          ↓
       Chunking
          ↓
      Embeddings
          ↓
      Apache Solr
```

## Search

```text
     User Query
          ↓
   Svelte Frontend
          ↓
        FastAPI
          ↓
   Candidate Retrieval
          ↓
        Ranking
          ↓
 Webpage-level Results
```

## Separation of responsibilities

The system separates:

- **Collection** — browser extension
- **Presentation** — Svelte frontend
- **Application logic** — FastAPI
- **Representation** — Sentence Transformer embeddings
- **Storage and search** — Apache Solr
- **Retrieval and ranking** — backend retrieval module
- **Optional summarization** — Gemini integration

This separation keeps the browser, user interface, processing, storage, and retrieval concerns independent.
