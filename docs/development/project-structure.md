# Project Structure

```text
ucs503p-202627-MemoryLane/
├── code/src/                  The application (see below)
├── docs/                      This documentation (MkDocs)
├── mkdocs.yml                 Documentation site config
├── assets/                    Images and theme files for the docs
├── journals/                  Project journals
├── project-proposal/          Course deliverables
├── project-report-prototype-stage/
└── project-report-final/
```

## Application

```text
code/src/
├── backend/                   FastAPI app (see Backend Architecture)
├── frontend/                  Svelte 4 + Vite web app
├── extension/                 Chrome extension (Manifest V3)
├── scripts/                   Solr setup, schema additions, re-index, backfill
├── evaluation/                SciFact benchmark and generated-query evaluation
├── tests/                     pytest suite
├── deploy/
│   ├── README.md              Step-by-step EC2 deployment guide
│   └── caddy/                 Caddyfile + image that builds the web app and extension zip
├── docs/                      Implementation plan
├── docker-compose.yml         solr + backend + caddy
├── requirements.txt
├── pytest.ini
└── .env.example               Every setting, with defaults
```

## Where to look

| To change... | Start in |
| --- | --- |
| How pages are cleaned or chunked | `backend/cleaning.py`, `backend/chunking.py` |
| How a page is saved | `backend/ingest.py` |
| Ranking | `backend/retrieval.py`, `backend/config.py` |
| Snippets | `backend/snippets.py` |
| The library map | `backend/library_map.py`, `frontend/src/lib/mapView.js`, `frontend/src/components/map/` |
| What's allowed per user | `backend/auth.py`, `backend/solr_client.py` |
| The Solr schema | `scripts/setup_solr.sh` (and its PowerShell mirror) |
| What auto-capture skips | `extension/page_filter.js` |
| Colours and type | `frontend/src/styles/tokens.css`, `extension/tokens.css` |
