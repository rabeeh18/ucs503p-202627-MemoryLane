# Configuration

Settings come from `code/src/.env`. Start from `.env.example`. The `.env` file holds secrets and is ignored by git.

## Sign-in (Amazon Cognito)

The API refuses to start without a Cognito pool. Create one with:

- An **app client** with no client secret (a public client using PKCE), the **Authorization code** grant, and the scopes `openid`, `email` and `profile`.
- **Allowed callback URLs**: `https://<your-domain>/auth/callback`, `http://localhost:5173/auth/callback`, and the extension's `https://<extension-id>.chromiumapp.org/`.
- **Allowed sign-out URLs**: `https://<your-domain>/` and `http://localhost:5173/`.
- **Identity providers**: the Cognito user pool, and optionally Google.

| Variable | Purpose |
| --- | --- |
| `COGNITO_REGION`, `COGNITO_USER_POOL_ID`, `COGNITO_APP_CLIENT_ID` | The pool whose access tokens the API accepts |
| `VITE_COGNITO_DOMAIN` | Hosted sign-in domain, e.g. `https://<prefix>.auth.<region>.amazoncognito.com` |
| `VITE_COGNITO_CLIENT_ID` | Same app client id, used by the web app |
| `VITE_REDIRECT_URI`, `VITE_LOGOUT_URI` | Where Cognito returns after sign-in and sign-out |
| `VITE_API_BASE` | Where the web app sends API calls (`/api` behind Caddy; the dev server proxies it) |
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API (default `http://localhost:5173`) |

## Solr and embeddings

| Variable | Default | Purpose |
| --- | --- | --- |
| `SOLR_URL` | `http://localhost:8983/solr/memorylane_v2` | Core URL |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Sentence Transformers model (`all-MiniLM-L6-v2` also works) |
| `EMBEDDING_DIM` | `384` | Must match the Solr vector field |
| `EMBEDDING_QUERY_PREFIX` | BGE search instruction | Added to queries only; leave empty for MiniLM |

Changing the model means re-embedding every page.

## Retrieval

| Variable | Default | Purpose |
| --- | --- | --- |
| `DEFAULT_TOP_K` | `5` | Pages returned when a request doesn't say |
| `DEFAULT_CANDIDATE_POOL` | `50` | Chunks fetched from BM25 and from KNN |
| `RRF_K` | `60` | Reciprocal Rank Fusion constant |
| `BM25_WEIGHT`, `VECTOR_WEIGHT` | `1.0`, `1.0` | Weights of the two rankings |
| `PAGE_SECOND_CHUNK_WEIGHT` | `0.3` | How much a page's second-best chunk adds |
| `MIN_VECTOR_SIMILARITY` | `0.55` | Pages with no keyword match need at least this cosine similarity |
| `RERANK_ENABLED`, `RERANK_MODEL`, `RERANK_TOP_N` | `false`, `cross-encoder/ms-marco-MiniLM-L-6-v2`, `20` | Optional cross-encoder reranker (more memory) |

## Chunking

| Variable | Default | Purpose |
| --- | --- | --- |
| `CHUNK_MAX_WORDS` | `150` | Largest chunk |
| `CHUNK_MIN_WORDS` | `40` | A last chunk with fewer new words merges into the previous one |
| `CHUNK_OVERLAP_WORDS` | `30` | Words carried over from the previous chunk |

## Library map

| Variable | Default | Purpose |
| --- | --- | --- |
| `MAP_MAX_PAGES` | `2000` | Most recent pages placed on the map |
| `MAP_MIN_PAGES` | `10` | Below this, the map asks you to save a few more |
| `MAP_OUTLIER_SIMILARITY` | `0.35` | Pages less similar than this to their topic's centre stay unclustered |
| `MAP_CROSS_TOPIC_SIMILARITY` | `0.65` | Topics at least this similar get a dashed link |
| `MAP_CACHE_USERS`, `MAP_CACHE_TTL_SECONDS` | `50`, `600` | In-memory map cache |

## Gemini

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | empty | Leave empty to turn off summaries and Gemini topic names |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Model id |

## Deployment

| Variable | Purpose |
| --- | --- |
| `DOMAIN` | Domain Caddy gets a certificate for (the `www.` name redirects to it) |
| `SOLR_HEAP` | Solr's Java heap (default `1g`) |
| `SOLR_VOLUME` | Docker volume holding Solr's data |
| `API_HOST`, `API_PORT` | Uvicorn bind address when running without Docker (`0.0.0.0`, `8000`) |

## Extension

`extension/config.js` holds the website URL, API URL and Cognito settings the extension uses. The extension's ID is pinned by the `key` in `manifest.json`, so its sign-in redirect URL stays the same on every install.
