# 0015. Run the server's saving code in the browser with Pyodide

**Status:** Accepted · **Date:** November 2026

## Context

A page saved on the device must become exactly the chunks the server would make, or local and server search diverge before they start. The server's saving pipeline is Python: trafilatura extracts the article from the HTML, then the project's own cleaning, chunking, title and description rules (`backend/ingest.py`). trafilatura has no JavaScript equivalent; Mozilla's Readability extracts differently.

## Decision

Run the **same Python** in the extension with Pyodide (CPython compiled to WebAssembly):

- `extension/tools/vendor.mjs` bundles Pyodide, the compiled `lxml` and `regex` packages, and the pure-Python wheels trafilatura needs, pinned and hash-checked, plus the backend's modules (`ingest.py`, `cleaning.py`, `chunking.py`, `url_utils.py`, `page_filter.py`, ...). Nothing is loaded from the internet at run time (Manifest V3 forbids remote code).
- `extension/engine/py/local_ingest.py` calls `ingest_page` exactly as `POST /memory` does, with a stand-in for Solr that answers from the local index and captures the chunks, and with embedding deferred to the browser's model.

## Alternatives

| Option | Why not |
| --- | --- |
| Port the cleaning to JavaScript with Readability | Different extraction: different chunks, different results |
| Send the HTML to the server to clean | Defeats the point: the server would see every page |
| Keep the HTML and clean on demand | Same problem, later |

## Consequences

- **Easier:** one implementation of saving. On ten real pages (Wikipedia, MDN, the Python docs, BBC, GitHub, Hacker News, and pages refused for too little text) the extension produced exactly the server's chunks, titles, descriptions and refusals.
- **Harder:** the extension carries ~18 MB of Python runtime, and Pyodide takes 2 to 4 seconds to start (it starts on the first save and stays loaded while the engine is open). The backend modules it imports must keep their network clients optional (`httpx`, YouTube) or stubbed, as `local_ingest.py` does.
