# MemoryLane

**Find the page you saved, even when you forget its name.**

MemoryLane is a personal memory for the web. You save pages as you browse, with one click or automatically, and later find them by describing what they were about. You don't need the title, the address or the exact words.

| | |
| --- | --- |
| **Live app** | [memorylane.site](https://memorylane.site) |
| **Documentation** | [rabeeh18.github.io/ucs503p-202627-MemoryLane](https://rabeeh18.github.io/ucs503p-202627-MemoryLane/) |
| **Chrome extension** | [memorylane.site/extension](https://memorylane.site/extension) |
| **Course** | UCS503 Software Engineering, Thapar Institute of Engineering and Technology, 2026–27 |

---

## What it does

- **Save pages** from a Chrome extension with one click, with undo.
- **Automatic capture** (off by default) saves only pages you actually read that look like content. It never saves email, banking, social media, private apps or login pages, and you can exclude any site.
- **Search by meaning or by exact words.** Keyword search (BM25) and meaning search (vector KNN) run together and are combined with Reciprocal Rank Fusion.
- **Say where or when**: *"the reddit post about rust lifetimes from last week"* ranks pages from that site and time first.
- **Readable snippets** show the sentences that match, and **summaries** (Google Gemini) are one click away.
- **YouTube videos** are saved through their captions. **Voice search** works in Chrome and Edge.
- **Private accounts**: sign in with Google or email (Amazon Cognito). Every page belongs to one account, and you can delete one page or all your data at any time.

## How it works

```text
Browse ─▶ Save ─▶ Clean (trafilatura) ─▶ Chunk (150 words) ─▶ Embed (bge-small-en-v1.5) ─▶ Store (Solr)
                                                                                              │
Results ◀─ Snippets ◀─ Relevance floor ◀─ Group into pages ◀─ RRF ◀─ BM25 + vector search ◀───┘
```

| Part | Technology |
| --- | --- |
| Backend | Python 3.11, FastAPI, Sentence Transformers, trafilatura |
| Search | Apache Solr 9.7: BM25 and HNSW vectors in one core |
| Web app | Svelte 4, Vite |
| Extension | Chrome Manifest V3 |
| Sign-in | Amazon Cognito (OAuth 2.0 authorization code with PKCE) |
| Summaries | Google Gemini (optional) |
| Hosting | One AWS EC2 instance, Docker Compose, Caddy (automatic HTTPS) |
| Documentation | MkDocs Material, with meaning-based docs search (Model2Vec) |

## Search quality

Measured on the SciFact benchmark (100 claims, 1,000 abstracts) with the production code:

| Configuration | Hit@1 | Hit@10 | MRR@10 | nDCG@10 |
| --- | ---: | ---: | ---: | ---: |
| Hybrid (live search) | 0.71 | 0.93 | 0.786 | 0.810 |
| Vector only | 0.75 | 0.94 | 0.812 | 0.837 |
| BM25 only | 0.63 | 0.86 | 0.705 | 0.728 |

A search takes about 76 ms (median, in-process). The full results, with confidence intervals, are in [Evaluation Results](https://rabeeh18.github.io/ucs503p-202627-MemoryLane/evaluation/results/).

## Getting started

**To use MemoryLane**, open [memorylane.site](https://memorylane.site), sign in, and install the extension. The [Tutorial](https://rabeeh18.github.io/ucs503p-202627-MemoryLane/getting-started/) walks through your first saved page and search in about ten minutes.

**To run your own copy**, you need Python 3.10+, Node 20+, Docker, and an Amazon Cognito user pool:

```bash
git clone https://github.com/rabeeh18/ucs503p-202627-MemoryLane.git
cd ucs503p-202627-MemoryLane/code/src
cp .env.example .env                  # fill in the Cognito ids; Gemini is optional
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

docker compose up -d solr             # Solr 9.7 on 127.0.0.1:8983
docker compose exec solr solr create -c memorylane_v2 -d _default
CORE_NAME=memorylane_v2 ./scripts/setup_solr.sh

uvicorn backend.main:app --reload --port 8000     # the API
cd frontend && npm install && npm run dev          # the web app on :5173
```

Then load `code/src/extension` as an unpacked extension in Chrome. Step-by-step instructions, Windows commands and every setting are in [Installation](https://rabeeh18.github.io/ucs503p-202627-MemoryLane/development/installation/) and [Configuration](https://rabeeh18.github.io/ucs503p-202627-MemoryLane/development/configuration/).

## Tests

```bash
cd code/src && python -m pytest -q             # 430 backend tests
cd code/src/frontend && npm test && npm run check   # 136 frontend tests + type check
```

GitHub Actions runs both suites on every push (`.github/workflows/ci.yml`) and checks that the documentation builds (`.github/workflows/mkdocs.yml`).

## Documentation

| | |
| --- | --- |
| [Tutorial](https://rabeeh18.github.io/ucs503p-202627-MemoryLane/getting-started/) | Your first saved page and search, step by step |
| [Usage Guide](https://rabeeh18.github.io/ucs503p-202627-MemoryLane/user-guide/automatic-capture/) | Every feature: saving, searching, the library, summaries, YouTube, voice |
| [API Reference](https://rabeeh18.github.io/ucs503p-202627-MemoryLane/api/) | Every endpoint, with requests, responses, errors and rate limits |
| [Architecture](https://rabeeh18.github.io/ucs503p-202627-MemoryLane/architecture/overview/) | Components, data flow, retrieval and security |
| [Design Decisions](https://rabeeh18.github.io/ucs503p-202627-MemoryLane/decisions/) | Eleven architecture decision records |
| [Deployment](https://rabeeh18.github.io/ucs503p-202627-MemoryLane/development/deployment/) | Running it on a server |

## Repository

[`MANIFEST.md`](MANIFEST.md) lists every folder and important file. In short:

```text
code/src/            the application: backend, frontend, extension, tests, evaluation, deployment
docs/                the documentation site (MkDocs)
journals/            weekly project journals
project-proposal/    course deliverables: proposal, prototype report, final report
project-report-*/
```

## Team

| Roll number | Name |
| --- | --- |
| 1024030716 | Rabeeh Ahmad |
| 1024030719 | Ishan Singhania |

Group 3C51, BE Third Year, Computer Science and Engineering. Supervisor: Dr. Raghav B. Venkataramaiyer.

## License

MemoryLane is released under the [MIT License](LICENSE). Some files in this repository come from others and keep their own terms:

| Material | Location | Terms |
| --- | --- | --- |
| IBM Plex fonts | `code/src/extension/fonts/` | SIL Open Font License 1.1 (`LICENSE-OFL.txt`) |
| SciFact dataset (subset) | `code/src/evaluation/scifact_data/` | CC BY-NC 2.0, from Allen Institute for AI; for evaluation only |
| Thapar Institute logo | `assets/tiet-logo.*` | Trademark of TIET; not covered by the MIT License |

Models (`BAAI/bge-small-en-v1.5`, Model2Vec `potion-base-8M`) and libraries are downloaded at install or build time under their own licenses and are not part of this repository.
