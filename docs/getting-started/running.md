# Running MemoryLane

## The hosted site

MemoryLane runs at **[memorylane.site](https://memorylane.site)**.

1. **Sign in** with **Continue with Google** or with email. Each account has its own private, empty library.
2. **Get the extension** from **[memorylane.site/extension](https://memorylane.site/extension)**:
    1. Download `memorylane-extension.zip` and unzip it.
    2. Open `chrome://extensions` and turn on **Developer mode**.
    3. Click **Load unpacked** and choose the unzipped folder.
    4. Pin MemoryLane to the toolbar, open it, and sign in.
3. **Save pages** with **Remember this page** in the extension popup. You can also turn on automatic capture there.
4. **Search** on the website by describing what you remember. Your library, the map and related pages fill up as you save more.

Once the extension is installed, the website stops showing "Get the extension".

## Running it locally

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

### Command-line search

Search a user's pages without the web app:

```bash
python -m backend.cli "your query" --user-id <cognito-sub> --top-k 5 --debug --no-summarize
```

`--debug` prints each page's BM25 rank, KNN rank, fused score and timings.

## Running it on a server

The production setup is Docker Compose with Solr, the backend and Caddy on one machine. See [Deployment](../development/deployment.md).
