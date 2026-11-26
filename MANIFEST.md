# Manifest

Everything in the MemoryLane repository: what each folder and important file is for, what is generated, and what comes from third parties.

## Top level

| Path | Contents |
| --- | --- |
| `README.md` | Project overview, quick start, team, license summary |
| `MANIFEST.md` | This file |
| `LICENSE` | MIT License |
| `code/src/` | The application (see below) |
| `docs/` | Source of the documentation site (Markdown, built with MkDocs) |
| `mkdocs.yml` | Documentation site configuration and navigation |
| `hooks/semantic_search.py` | MkDocs build hook that creates the meaning-based docs search |
| `includes/abbreviations.md` | Abbreviation tooltips added to every docs page |
| `assets/` | Images, icons and theme overrides used by the docs |
| `journals/` | Weekly project journals, one folder per student (roll number and name) |
| `project-proposal/` | Project proposal (LaTeX source and PDF) |
| `project-report-prototype-stage/` | Mid-semester report (LaTeX source, PDF, TIET report class) |
| `project-report-final/` | End-semester report: chapters, TikZ figures, screenshots, bibliography, PDF |
| `pyproject.toml` | Python project metadata |
| `Makefile` | Docs helper targets from the course template |
| `.github/workflows/ci.yml` | Runs the backend and frontend test suites on every push |
| `.github/workflows/mkdocs.yml` | Checks that the documentation builds in strict mode |

## Application (`code/src/`)

| Path | Contents |
| --- | --- |
| `backend/` | FastAPI application: API, sign-in checks, saving pipeline, search, snippets, summaries, problem reports |
| `backend/Dockerfile` | Image for the API (Python 3.11, CPU-only PyTorch) |
| `frontend/` | Svelte web app: search, library, account menu, landing and privacy pages |
| `extension/` | Chrome extension (Manifest V3): popup, options page, service worker, content scripts |
| `tests/` | Backend tests (pytest) |
| `frontend/src/**/*.test.js` | Frontend and extension-logic tests (Vitest) |
| `evaluation/` | SciFact benchmark, personal-library evaluation and the compare tool |
| `evaluation/scifact_report.json` | Latest benchmark results |
| `scripts/` | Solr schema setup (`setup_solr.sh`, `setup_solr.ps1`), field additions, re-index and backfill |
| `deploy/` | Server deployment guide and the Caddy image (HTTPS, static files, `/api` proxy) |
| `docs/` | Implementation plan and HTML design mock-ups for the web app and extension |
| `docker-compose.yml` | The three services: `solr`, `backend`, `caddy` |
| `requirements.txt` | Python packages for the server image |
| `requirements-dev.txt` | The same plus test tools |
| `pytest.ini` | Test configuration |
| `.env.example` | Every setting, with defaults; copy to `.env` |
| `README.md` | Developer reference for the application |

### Backend modules (`code/src/backend/`)

| Module | Responsibility |
| --- | --- |
| `main.py` | API endpoints, rate limits, log filtering, re-checking automatic saves |
| `auth.py` | Verifying Cognito access tokens |
| `accounts.py` | Linking Google and email sign-ins by verified email |
| `library_moves.py` | Moving pages into a linked library in the background |
| `ingest.py` | Saving a page: canonical URL, cleaning, chunking, embedding, storing |
| `cleaning.py`, `chunking.py` | Main-text extraction; 150-word overlapping chunks |
| `embeddings.py` | Loading the embedding model; passage and query embeddings |
| `retrieval.py` | BM25 + vector search, Reciprocal Rank Fusion, page grouping, relevance floor |
| `query_intent.py` | Site words, time phrases and URLs in a query |
| `snippets.py` | Choosing the sentences shown under each result |
| `rerank.py` | Optional cross-encoder reranker |
| `solr_client.py` | All Solr access, with the per-user filter built in |
| `page_filter.py` | Pages automatic capture must refuse |
| `summarizer.py` | Gemini summaries |
| `reports.py` | Storing problem reports and emailing them |
| `youtube_utils.py` | YouTube video ids and transcripts |
| `url_utils.py` | URL normalisation and page ids |
| `models.py` | Request and response models |
| `config.py` | Settings read from the environment |
| `cli.py` | Command-line search for debugging |

## Generated, not committed

| Path | What creates it |
| --- | --- |
| `site/` | `mkdocs build` (the published documentation) |
| `code/src/.venv/`, `code/src/frontend/node_modules/` | Installing the Python and Node dependencies |
| `code/src/frontend/dist/` | `npm run build` (the Caddy image builds it during deployment) |
| `code/src/data/` | Local SQLite databases (`accounts.db`, `reports.db`) |
| `code/src/.env` | Your settings, including secrets; never commit it |
| LaTeX `*.aux`, `*.log`, `*.bbl`, … | Building the reports |

On the server, Docker volumes hold Solr's index (`solr_data`), the downloaded models (`models`), the SQLite databases (`accounts`) and Caddy's certificates (`caddy_data`).

## Third-party material

| Material | Location | Terms |
| --- | --- | --- |
| IBM Plex fonts | `code/src/extension/fonts/` | SIL Open Font License 1.1 (`LICENSE-OFL.txt` alongside) |
| SciFact dataset (subset) | `code/src/evaluation/scifact_data/` | CC BY-NC 2.0, Allen Institute for AI; used for evaluation only |
| Thapar Institute logo | `assets/tiet-logo.png`, `assets/tiet-logo.svg` | Trademark of TIET, used for the course documentation |
| TIET report class | `project-report-*/tietreport.cls` | Course template |

Downloaded at install or build time, not stored in the repository: the embedding model `BAAI/bge-small-en-v1.5` (MIT), the optional reranker `cross-encoder/ms-marco-MiniLM-L-6-v2`, the docs-search model Model2Vec `potion-base-8M` (MIT), and the Python and npm packages listed in `requirements*.txt` and `package.json`.
