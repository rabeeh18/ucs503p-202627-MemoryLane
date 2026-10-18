# Deploying MemoryLane on one EC2 instance

Everything runs from `code/src` with Docker Compose:

| Service | What it does | Reachable from |
|---|---|---|
| `solr` | Solr 9.7, data in the `src_solr_data` volume | `127.0.0.1:8983` on the instance only |
| `backend` | FastAPI + embedding model (`/models` volume) | Caddy only (no published port) |
| `caddy` | HTTPS for `memorylane.site`, serves the built frontend, proxies `/api/*` to the backend, redirects `www.` | ports 80 and 443 |

Instance: c7i-flex.large (4 GB RAM), Elastic IP `13.201.221.52`. Solr gets a 1 GB heap; the reranker stays off.

This guide moves the instance from the **current setup** (the `master` branch with the backend run directly by Python on port 8000, Solr from the old `docker-compose.yml` with the core `memorylane`, and the Vercel frontend calling port 8000) to the new stack **without losing the old core**, then re-indexes your pages under your Cognito account.

Paths below assume the repository is cloned at `~/ucs503p-202627-MemoryLane`. Adjust if yours differs.

---

## 0. Before you start (AWS console, DNS)

1. **Cognito app client** (`2peosqda8lrs1q4ud0bi0etklq`), under *App integration → App client → Login pages*:
   - Allowed callback URLs:
     - `https://memorylane.site/auth/callback`
     - `http://localhost:5173/auth/callback`
     - `https://igdbkkmpnplmboeccgigbjgoefecdhck.chromiumapp.org/` (the extension)
   - Allowed sign-out URLs: `https://memorylane.site/` and `http://localhost:5173/`
   - Identity providers: **Google** and **Cognito user pool**. OAuth grant: **Authorization code**. Scopes: `openid`, `email`, `profile`.
2. **DNS**: `memorylane.site` already has an `A` record for `13.201.221.52`. Add the same for `www.memorylane.site` (an `A` record, or a `CNAME` to `memorylane.site`), so Caddy can get a certificate for the redirect.
3. **Security group**: allow inbound **80** and **443** from anywhere. Leave 8000 and 8983 as they are for now; step 12 closes them.
4. **Snapshot** the instance's EBS volume (EC2 → Volumes → Create snapshot). It's your rollback point.

---

## 1. Add 2 GB of swap

The embedding model, Solr and the first Docker build together come close to 4 GB.

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf
sudo sysctl --system
free -h          # Swap: 2.0Gi
```

## 2. Check Docker

Docker already runs the old Solr. Check that Compose and Buildx are present and that Docker starts on boot:

```bash
docker compose version
docker buildx version
sudo systemctl enable docker
```

If `docker buildx` is missing: on Ubuntu, `sudo apt-get install docker-buildx-plugin docker-compose-plugin`. On Amazon Linux 2023, download the `buildx` release binary for `linux-amd64` into `~/.docker/cli-plugins/docker-buildx` and `chmod +x` it.

## 3. Find the old Solr volume

```bash
docker inspect memorylane-solr --format '{{range .Mounts}}{{.Name}}{{"\n"}}{{end}}'
docker volume ls | grep solr_data
```

The old compose file, run from `code/src`, names the volume **`src_solr_data`**, and the new `docker-compose.yml` uses that name. If yours is different, write it down: it goes into `SOLR_VOLUME` in step 6.

## 4. Stop the old backend and the old Solr

This starts the downtime. The Vercel site stops working until step 9.

```bash
# The Python backend on port 8000: find out how it runs.
sudo ss -ltnp 'sport = :8000'
systemctl list-units --type=service | grep -i -E 'memorylane|uvicorn'
```

- If it's a systemd service: `sudo systemctl disable --now <service-name>`, so it doesn't come back after a reboot.
- If it's in `tmux`/`screen`/`nohup`: stop it there, or `kill <pid>` using the pid from `ss`. Also remove any `@reboot` line from `crontab -e`.

Then stop the old Solr. **Never add `-v`**, which would delete the volume and the old core:

```bash
cd ~/ucs503p-202627-MemoryLane/code/src
docker compose down           # the OLD compose file, still checked out
docker volume ls | grep solr_data    # the volume must still be listed
```

Optional extra backup of the core files (Solr is stopped, so the copy is consistent):

```bash
docker run --rm -v src_solr_data:/v -v ~/:/backup alpine tar czf /backup/solr_data_backup.tgz -C /v .
```

## 5. Update the code

Push the new commits from your machine first (`git push origin master`). Then on the instance:

```bash
cd ~/ucs503p-202627-MemoryLane
cp code/src/.env ~/memorylane.env.old 2>/dev/null || true   # keep the old settings (Gemini key)
git pull origin master
```

## 6. Create `.env`

```bash
cd ~/ucs503p-202627-MemoryLane/code/src
cp .env.example .env
nano .env
```

- Set `GEMINI_API_KEY` (copy it from `~/memorylane.env.old`). Leave it empty to turn summaries off.
- Set `SOLR_VOLUME` if step 3 found a name other than `src_solr_data`.
- The domain, Cognito and `VITE_*` values are already filled in for `memorylane.site`.

## 7. Start Solr and create the new core

```bash
docker compose up -d solr
docker compose ps                          # wait for solr to be "healthy"
curl -s 'http://127.0.0.1:8983/solr/admin/cores?action=STATUS&wt=json' | python3 -c "import sys,json; print(list(json.load(sys.stdin)['status']))"
# -> ['memorylane']   (the old core survived)

docker compose exec solr solr create -c memorylane_v2 -d _default
CORE_NAME=memorylane_v2 bash scripts/setup_solr.sh
```

The setup script (it needs `curl` and `python3` on the instance) installs schema v2 and ends with a smoke test: index, BM25 with stemming, KNN with a user filter, delete. It must finish with "MemoryLane Solr setup complete!".

## 8. Build and start everything

```bash
docker compose up -d --build        # first build: 5-10 minutes (CPU torch, npm build)
docker compose logs -f backend      # wait for "Embedding model loaded", then Ctrl+C
docker compose logs caddy | grep -i -E 'certificate obtained|error'
```

The first backend start downloads `BAAI/bge-small-en-v1.5` into the `models` volume, so it only happens once.

## 9. Check the site

```bash
curl -s https://memorylane.site/api/health
# {"status":"ok","solr":true,"embedding_model":true,"gemini":true}
curl -sI https://www.memorylane.site | grep -i location     # -> https://memorylane.site/
```

Open `https://memorylane.site` and sign in with **Continue with Google**. The library is empty for now.

> Google sign-in and email sign-in create **separate** Cognito users with different `sub`s unless you link them. Pick the one you'll use and re-index under it.

## 10. Re-index your old pages under your Cognito user

Find your user id: Cognito console → User pool → **Users** → your user → **User ID (sub)**. It looks like `4c1d6f2a-90b1-70e3-…`.

```bash
cd ~/ucs503p-202627-MemoryLane/code/src
docker compose exec backend python -m scripts.reindex \
  --source-core memorylane --target-core memorylane_v2 --user-id <your-sub> --dry-run

docker compose exec backend python -m scripts.reindex \
  --source-core memorylane --target-core memorylane_v2 --user-id <your-sub> --delete-user legacy
```

- The dry run prints how many pages and chunks it found.
- `--delete-user legacy` removes anything indexed earlier under the placeholder user `legacy`. It's harmless if there is none.
- Pages with fewer than 50 readable words are reported as failures and skipped.
- The source core is never modified.

Refresh the website: your pages appear under **Recently saved**.

## 11. Hand-check search quality (about 15 minutes)

Write 15–20 queries for pages you know you saved, and note where the expected page lands. Things to try:

- `RERANK_ENABLED=true` in `.env`, then `docker compose up -d backend`. It needs more memory; watch `free -h`.
- If BGE looks worse than MiniLM on your queries: set `EMBEDDING_MODEL=all-MiniLM-L6-v2` and `EMBEDDING_QUERY_PREFIX=`, restart the backend, and re-run step 10. Changing the model re-embeds every page.

For debugging, `POST /api/search` with `"debug": true` returns ranks and `timings` (`total_ms` should be under ~300 ms without the reranker).

## 12. Close the old ports

In the security group, **remove** the inbound rules for 8000 and 8983, and limit 22 to your IP. From your own computer, both of these should time out:

```bash
curl -m 5 http://13.201.221.52:8000/health
curl -m 5 http://13.201.221.52:8983/solr/
```

Solr is bound to `127.0.0.1`, and the backend publishes no port at all, so they stay private even if a rule is left open by mistake.

## 13. Install the extension

`chrome://extensions` → Developer mode → **Load unpacked** → `code/src/extension`. The ID must be `igdbkkmpnplmboeccgigbjgoefecdhck`. Sign in from the popup and save a page.

## 14. Reboot test

```bash
sudo reboot
# after it's back:
cd ~/ucs503p-202627-MemoryLane/code/src && docker compose ps     # all services up
curl -s https://memorylane.site/api/health
```

## 15. Backups

Create an **Amazon Data Lifecycle Manager** policy (EC2 → Lifecycle Manager): target the instance's EBS volume by tag, daily snapshot, retain 7.

## 16. Clean up

- Once the new site works, delete the Vercel project.
- After you're happy with the re-indexed library, unload the old core. This keeps its files on disk; add `&deleteInstanceDir=true` to remove them:

  ```bash
  curl 'http://127.0.0.1:8983/solr/admin/cores?action=UNLOAD&core=memorylane'
  ```

---

## Day-to-day

```bash
cd ~/ucs503p-202627-MemoryLane/code/src
git pull origin master && docker compose up -d --build     # deploy a new version
docker compose logs -f backend                               # API logs
docker compose restart backend                               # after editing .env
```

### Schema changes

Some updates add a Solr field. The core has automatic field creation turned off, so **add the field before deploying the backend that writes it**, or saves fail.

- **`description`** (paragraph snippets):

  ```bash
  git pull origin master
  CORE_NAME=memorylane_v2 bash scripts/add_description_field.sh
  docker compose up -d --build
  ```

  Existing pages get a description the next time they're saved: a page stored without one is re-ingested even if its text hasn't changed. Until then their snippets come from their text, and only pages with no readable sentence show none. To fill every page at once, re-run the re-index from the old core (if you still have it), which re-ingests each page under your user id:

  ```bash
  docker compose exec backend python -m scripts.reindex --source-core memorylane --target-core memorylane_v2 --user-id <your-sub>
  ```

**Never** run `docker compose down -v`: it deletes Solr's data, the downloaded models and Caddy's certificates.

## Troubleshooting

| Symptom | Check |
|---|---|
| No HTTPS certificate | Ports 80/443 open in the security group; `dig +short memorylane.site` returns `13.201.221.52`; `docker compose logs caddy` |
| Backend restarting | `docker compose logs backend`. A missing `COGNITO_*` value stops startup with a clear message; out of memory shows as exit code 137 (check `free -h` and swap) |
| `/api/health` says `solr: false` | `docker compose ps solr`; the `memorylane_v2` core exists (step 7) |
| Sign-in loops or says "redirect_mismatch" | The callback and sign-out URLs in step 0 match exactly, including the trailing `/` |
| Extension sign-in fails | The extension ID is `igdbkkmpnplmboeccgigbjgoefecdhck` and its `chromiumapp.org` URL is in the callback list |
| Old core missing after step 7 | Wrong volume: stop the stack, set `SOLR_VOLUME` to the name from step 3, then start again |
