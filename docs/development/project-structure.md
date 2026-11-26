--8<-- "MANIFEST.md"

## Where to look

| To change... | Start in |
| --- | --- |
| How pages are cleaned or chunked | `backend/cleaning.py`, `backend/chunking.py` |
| How a page is saved | `backend/ingest.py` |
| Ranking | `backend/retrieval.py`, `backend/config.py` |
| Snippets | `backend/snippets.py` |
| What's allowed per user | `backend/auth.py`, `backend/solr_client.py` |
| The Solr schema | `scripts/setup_solr.sh` (and its PowerShell mirror) |
| What auto-capture skips | `extension/page_filter.js` and `backend/page_filter.py` |
| Colours and type | `frontend/src/styles/tokens.css`, `extension/tokens.css` |

This page is generated from `MANIFEST.md` at the repository root.
