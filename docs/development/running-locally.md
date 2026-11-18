# Running Locally

After [installation](installation.md) and [configuration](configuration.md), with Solr running:

```bash
# API (from code/src)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
curl http://localhost:8000/health
# {"status":"ok","solr":true,"embedding_model":true,"gemini":true}
```

```bash
# Web app (from code/src/frontend)
npm run dev        # http://localhost:5173, proxies /api to http://127.0.0.1:8000
```

`/health` reports `status: ok` when Solr and the embedding model are ready. Gemini is optional, so `gemini: false` is fine.

To use the extension against your local API, load `code/src/extension` unpacked (`chrome://extensions` → **Developer mode** → **Load unpacked**) and point the endpoints in `extension/config.js` at it. See [Configuration](configuration.md#extension).

## Command-line search

Search a user's pages without the web app:

```bash
python -m backend.cli "your query" --user-id <cognito-sub> --top-k 5 --debug --no-summarize
```

`--debug` prints each page's BM25 rank, KNN rank, fused score and timings.

## Running it on a server

The production setup is Docker Compose with Solr, the backend and Caddy on one machine. See [Deployment](deployment.md).
