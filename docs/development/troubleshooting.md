# Troubleshooting

## Server (Docker Compose on EC2)

| Symptom | Check |
| --- | --- |
| No HTTPS certificate | Ports 80 and 443 are open in the security group; `dig +short <domain>` returns the server's Elastic IP; `docker compose logs caddy` |
| Backend keeps restarting | `docker compose logs backend`. A missing `COGNITO_*` value stops start-up with a clear message; running out of memory shows as exit code 137 (check `free -h` and swap) |
| `/api/health` says `solr: false` | `docker compose ps solr`, and the `memorylane_v2` core exists (see [Deployment](deployment.md#first-deployment)) |
| `/api/health` says `gemini: false` | `GEMINI_API_KEY` is set in `.env` and the backend was restarted (`docker compose up -d backend`). Summaries are optional |
| Summaries fail or are slow | `docker compose logs backend --since 10m`, and look for lines mentioning Gemini or summaries: an invalid key, an unknown `GEMINI_MODEL`, or a quota limit each log their own error |
| Problem reports aren't emailed | `SMTP_HOST`, `REPORTS_FROM` and `REPORTS_TO` are set; in the SES sandbox both addresses are verified; the log shows `Report #N emailed` or the SMTP error. Unsent reports are retried with backoff |
| Pages from a before-linking sign-in are missing | They're moved in the background after the sign-in links (`Library move finished` in the log). A failed move is retried every few minutes |
| Old core missing after a re-deploy | Wrong Docker volume: stop the stack, set `SOLR_VOLUME` to the old volume's name (`docker volume ls`), then start again |

!!! warning
    Never run `docker compose down -v`. It deletes Solr's data, the downloaded models and Caddy's certificates.

## Sign-in

| Symptom | Check |
| --- | --- |
| Sign-in loops, or Cognito says `redirect_mismatch` | The callback and sign-out URLs in the Cognito app client match exactly, including the trailing `/` |
| Extension sign-in fails | The extension ID is `igdbkkmpnplmboeccgigbjgoefecdhck`, and its `https://<id>.chromiumapp.org/` URL is in the callback list |
| Google and email sign-ins show different libraries | `COGNITO_DOMAIN` (or `VITE_COGNITO_DOMAIN`) is set, so linking is on, and the email address is verified |

## Extension

| Symptom | Check |
| --- | --- |
| "This page can't be saved" | Chrome doesn't let extensions read some pages (the Chrome Web Store, `chrome://` pages, PDFs) |
| A page isn't captured automatically | It may be on the skip list (banking, email, social, login and similar pages), an excluded site, or have too little text. **Remember this page** still saves it |
| YouTube videos won't save | The extension is version 2.2.0 or later (it fetches captions in the YouTube tab). A video needs captions, or a description of at least 15 words |
| A change to the extension doesn't show | Reload it on `chrome://extensions` |

## Local development

| Symptom | Check |
| --- | --- |
| `npm` isn't found, or PowerShell blocks `npm` | Use `npm.cmd`, or allow scripts once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| The first API start is slow | It downloads the embedding model (about 130 MB) once |
| `mkdocs build` warns that model2vec isn't installed | `pip install model2vec`; the docs' meaning-based search is built from it (see [Deployment](deployment.md#publishing-the-documentation)) |
