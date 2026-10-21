# Deployment

MemoryLane runs on one machine with Docker Compose. The live site is an AWS EC2 `c7i-flex.large` (2 vCPU, 4 GB RAM, plus 2 GB swap) in the Mumbai region, with an Elastic IP and the domain `memorylane.site`.

## Services

| Service | What it does | Reachable from |
| --- | --- | --- |
| `solr` | Solr 9.7 with a 1 GB heap; data in a named volume | `127.0.0.1:8983` on the server only |
| `backend` | FastAPI and the embedding model (cached in the `models` volume) | Caddy only; no published port |
| `caddy` | Gets HTTPS certificates, serves the built web app and the extension zip, proxies `/api/*` to the backend, redirects `www.` | Ports 80 and 443 |

```text
Browser / extension ──HTTPS──▶ Caddy ──/api──▶ FastAPI ──▶ Solr
                                 │
                                 └── web app (static) + /memorylane-extension.zip
```

The Caddy image builds the web app (`npm run build`) and zips the `extension/` folder, so `https://memorylane.site/memorylane-extension.zip` always matches the code being deployed.

## First deployment

From `code/src` on the server:

```bash
cp .env.example .env              # fill in Cognito, Gemini, DOMAIN
docker compose up -d solr
docker compose exec solr solr create -c memorylane_v2 -d _default
CORE_NAME=memorylane_v2 bash scripts/setup_solr.sh
docker compose up -d --build
curl -s https://<your-domain>/api/health
```

Before that, point the domain's `A` records (with and without `www.`) at the server and open ports 80 and 443. Ports 8000 and 8983 should stay closed.

The repository's `code/src/deploy/README.md` is the full step-by-step guide. It covers swap, moving data from an older core, the reboot test, and backups with EBS snapshots.

## Updating

```bash
cd code/src
git pull origin master
docker compose up -d --build
docker compose logs -f backend
```

Rebuilding the backend clears its in-memory map and label caches. Maps are rebuilt on the next request.

### Schema changes

Solr's automatic field creation is turned off, so a new field has to exist **before** the backend that writes it is deployed:

| Field | Added by | Then |
| --- | --- | --- |
| `description` | `scripts/add_description_field.sh` | Pages get one the next time they're saved |
| `page_embedding` | `scripts/add_page_embedding_field.sh` | `python -m scripts.backfill_page_vectors` gives older pages a page vector (resumable) |

!!! warning
    Never run `docker compose down -v`. It deletes Solr's data, the downloaded models and Caddy's certificates.

## Moving pages between cores

`scripts/reindex.py` copies pages from one core into another under a given user id, re-cleaning, re-chunking and re-embedding them. The source core is never modified.

```bash
docker compose exec backend python -m scripts.reindex \
  --source-core memorylane --target-core memorylane_v2 --user-id <cognito-sub> [--dry-run]
```
