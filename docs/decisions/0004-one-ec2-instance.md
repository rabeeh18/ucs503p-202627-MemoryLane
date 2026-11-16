# 0004. Run everything on one EC2 instance

**Status:** Accepted · **Date:** October 2026 · Replaces the Vercel-hosted frontend

## Context

In the prototype, the web app was hosted on Vercel and forwarded `/api` calls to the backend on an EC2 instance over **plain HTTP on port 8000**, so that port was open to the internet, and every change of the server's IP meant editing `vercel.json`. Going multi-user with Cognito sign-in meant the web app, the API and Solr had to work together reliably: one domain for sign-in redirects, HTTPS everywhere, no backend or Solr port exposed, and a deploy that one student can do and undo.

## Decision

Run Solr, the FastAPI backend and **Caddy** with **Docker Compose** on a single AWS EC2 instance (`c7i-flex.large`: 2 vCPU, 4 GB RAM plus 2 GB swap, Mumbai). Caddy gets HTTPS certificates automatically, serves the built web app and the extension zip, and proxies `/api/*` to the backend. Only ports 80 and 443 are open. Data lives in named Docker volumes, backed up with EBS snapshots.

## Alternatives

| Option | Why not |
| --- | --- |
| Keep the web app on Vercel and add HTTPS to the API | Two deploys and two domains, redirect URLs and the API address to keep in sync, for one small app |
| Managed services (hosted search, container platform) | Monthly cost well beyond a student budget, and more pieces to configure |
| Kubernetes | Far more operational work than three containers need |

## Consequences

- **Easier:** one `git pull && docker compose up -d --build` updates everything. The extension zip always matches the deployed code, because the Caddy image builds it.
- **Harder:** one machine is a single point of failure: no redundancy, and a rebuild means a few seconds of downtime.
- 4 GB of RAM is tight. Solr gets a 1 GB heap, and the optional cross-encoder reranker stays off. The plan originally asked for 8 GB.
- `docker compose down -v` would delete all data; the deployment guide warns about it.
