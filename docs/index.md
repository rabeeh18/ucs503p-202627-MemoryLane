# MemoryLane

## Find the page you saved, even when you forget its name

MemoryLane is a personal memory for the web. You save pages as you browse, with one click or automatically, and later find them by describing what they were about. You don't need the exact title, URL or wording.

**[Open MemoryLane →](https://memorylane.site)** · **[Get the extension →](https://memorylane.site/extension)**

```text
Browse → Save → Clean → Chunk → Embed → Store
                                          ↓
      Find ← Rank ← Fuse ← Keyword + meaning search ← Describe it
```

### What MemoryLane can do

- **One-click saving** from the Chrome extension, with undo
- **Automatic capture** (off by default) that skips sensitive and low-value pages and any site you exclude
- **Search by meaning or by exact words**: hybrid BM25 + vector search, fused with Reciprocal Rank Fusion
- **Readable snippets** that show the sentences matching your query
- **Library map**: your saved pages grouped into named topics on a zoomable map
- **Related pages** for any saved page
- **Search within a topic** from the map
- **On-demand summaries** of a single result (Gemini)
- **YouTube videos**, saved through their transcripts
- **Voice search** in browsers that support speech recognition
- **Private accounts**: sign in with Google or email; every page belongs to one account only
- **Export or delete** all your data at any time

## Why MemoryLane?

Browser history tells you *where* you went. MemoryLane helps you remember *what was there*.

Instead of an exact page or phrase, you can search for something like:

> "that article explaining how database query latency can be reduced"

MemoryLane searches the text of the pages you saved and returns the pages that match best, with the most relevant sentences shown.

## Main components

| Component | Role |
| --- | --- |
| Chrome extension (Manifest V3) | Saves the current page, auto-capture, excluded sites |
| Svelte web app | Search, library, map, related pages, summaries, account |
| Amazon Cognito | Sign-in (Google or email) for the web app and the extension |
| Caddy | HTTPS, serves the web app, proxies `/api` to the backend |
| FastAPI backend | Verifies tokens, saves pages, searches, builds the map |
| trafilatura | Extracts the readable text of a page |
| Sentence Transformers (`BAAI/bge-small-en-v1.5`) | 384-dimensional embeddings |
| Apache Solr 9.7 | Stores chunks; BM25 and vector (KNN) search |
| scikit-learn | Topic clustering for the library map |
| Gemini | Optional: result summaries and map topic names |

Everything runs with Docker Compose on a single AWS EC2 instance, served at [memorylane.site](https://memorylane.site).

## Explore the documentation

- **[Getting Started](getting-started/index.md)**: use the hosted site, or run your own copy.
- **[Using MemoryLane](user-guide/automatic-capture.md)**: saving, searching, the library and the map.
- **[How It Works](how-it-works/overview.md)**: follow a page from saving to search.
- **[Architecture](architecture/overview.md)**: components, retrieval, the map and security.
- **[API Reference](api/index.md)**: the backend endpoints.
- **[Development](development/project-structure.md)**: repository layout, tests and deployment.
- **[Evaluation](evaluation/methodology.md)**: the SciFact retrieval benchmark.
- **[Privacy](privacy.md)**: what is stored, who can see it and what leaves the server.
