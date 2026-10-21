# Installation

All application code is in `code/src` of the [repository](https://github.com/rabeeh18/ucs503p-202627-MemoryLane). Commands below run from that folder.

## Requirements

- **Python 3.10+**
- **Apache Solr 9.x** (9.7 is the tested version). Solr 8 has no `DenseVectorField`, so it won't work.
- **Node.js 18+** for the web app
- **Docker** (recommended, for Solr, or for the whole stack)
- **Chrome or Chromium** for the extension
- An **Amazon Cognito** user pool (see [Configuration](configuration.md))
- Optional: a **Google Gemini API key** for summaries and map topic names

## 1. Backend

```bash
git clone https://github.com/rabeeh18/ucs503p-202627-MemoryLane.git
cd ucs503p-202627-MemoryLane/code/src
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
```

The first start downloads the embedding model (`BAAI/bge-small-en-v1.5`, about 130 MB) from Hugging Face.

## 2. Solr

Start Solr 9.7, for example with the project's Compose file:

```bash
docker compose up -d solr
docker compose exec solr solr create -c memorylane_v2 -d _default
```

Then install the schema. The script is idempotent: it checks the Solr version, creates the core if needed, applies the fields, turns off automatic field creation, and finishes with a smoke test (indexing, BM25 with stemming, KNN with a user filter).

```bash
CORE_NAME=memorylane_v2 ./scripts/setup_solr.sh      # Linux / macOS
.\scripts\setup_solr.ps1                              # Windows PowerShell
```

Add `--reset` (or `-Reset`) to drop and recreate the core. This deletes its data.

## 3. Web app

```bash
cd frontend
npm install
```

The web app reads its `VITE_*` settings from the same `.env` file in `code/src`.

## 4. Extension

`chrome://extensions` → turn on **Developer mode** → **Load unpacked** → choose `code/src/extension`.

The extension talks to the hosted site by default. To point it at a local backend, change the endpoints in `extension/config.js`. See [Configuration](configuration.md#extension).
