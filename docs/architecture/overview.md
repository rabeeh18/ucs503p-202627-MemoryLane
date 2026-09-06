# Architecture

MemoryLane consists of four main application areas:

```text
┌─────────────────────┐
│   Browser Extension │
│   Capture + Filter  │
└──────────┬──────────┘
           │ HTTP / JSON
           ▼
┌─────────────────────┐
│    FastAPI Backend  │
│ Processing + Search │
└───────┬───────┬─────┘
        │       │
        ▼       ▼
┌───────────┐ ┌───────────────┐
│  Solr     │ │ Gemini        │
│ Storage + │ │ Optional      │
│ Search    │ │ Summarization │
└───────────┘ └───────────────┘
        ▲
        │
┌───────┴──────────────┐
│    Svelte Frontend   │
│ Search + Results     │
└──────────────────────┘
```

## Main components

### Browser extension

Responsible for collecting page information, applying automatic-capture eligibility rules, and sending eligible content to the backend.

### FastAPI backend

Acts as the application layer. It exposes the API, processes memories, creates embeddings, communicates with Solr, performs retrieval, and coordinates optional summarization.

### Svelte frontend

Provides the browser-facing search experience, result display, voice input, and summary interactions.

### Apache Solr

Stores chunk-level memories and supports both textual and vector retrieval.

### Gemini

Provides optional result summarization when configured.

## Data flow

The architecture separates collection from processing and presentation. The browser does not perform indexing or search itself; the backend coordinates those operations.
