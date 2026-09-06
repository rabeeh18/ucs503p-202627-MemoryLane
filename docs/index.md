# MemoryLane

## MemoryLane remembers so you do not have to

MemoryLane is a personal browser-memory system that captures useful web content and makes it searchable later. Instead of relying on an exact URL, page title, or keyword, you can describe what you remember and search through the content you previously encountered.

```text
Browse
  ↓
Capture
  ↓
Filter
  ↓
Process
  ↓
Store
  ↓
Search
  ↓
Find
```

### What MemoryLane can do

- **Automatic capture** of eligible webpages while you browse
- **Manual capture** when you explicitly want to remember a page
- **Content-aware search** using natural-language queries
- **Semantic search** for meaning-based matching
- **Lexical search** for exact terminology
- **YouTube memories** using available video transcripts
- **Voice search** from the web interface
- **Optional AI summaries** for individual results
- **Webpage-level results** even though content is stored in smaller chunks

## Why MemoryLane?

Browser history tells you *where* you went. MemoryLane is designed to help you remember *what was there*.

For example, instead of remembering an exact page or phrase, you can search for something like:

> "that article explaining how database query latency can be reduced"

MemoryLane searches the content it has stored and returns the webpages whose content best matches the query.

## Main components

| Component | Role |
| --- | --- |
| Browser extension | Captures and sends webpage content |
| FastAPI backend | Coordinates processing and API requests |
| Content processing | Cleans, validates, and chunks captured content |
| Sentence Transformer | Creates semantic representations |
| Apache Solr | Stores memories and performs search |
| Svelte frontend | Provides the search interface |
| Gemini | Optionally summarizes selected results |

## Explore the documentation

- **Getting Started** — setup documentation will be added here later.
- **Using MemoryLane** — understand the user-facing features.
- **How It Works** — follow a memory from capture to retrieval.
- **Architecture** — understand the implementation.
- **Search** — see how lexical and semantic retrieval work.
- **API Reference** — work with the backend endpoints.
- **Development** — understand the repository and tests.
- **Evaluation** — see the retrieval evaluation and results.
- **Privacy** — understand capture filtering and external summarization considerations.
