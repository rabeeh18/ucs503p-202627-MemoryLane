# Glossary

The terms these docs use. Anywhere in the documentation, you can hover over one of them (shown with a dotted underline) to see its meaning.

## Search

| Term | Meaning |
| --- | --- |
| **BM25** | A keyword ranking. It scores a passage by how often it uses the query's words, giving more weight to rare words and less to very long passages. |
| **Embedding** | A list of 384 numbers that represents what a passage means. Passages with similar meanings have embeddings that point in similar directions. MemoryLane uses `BAAI/bge-small-en-v1.5`. |
| **Cosine similarity** | How closely two embeddings point the same way, from -1 to 1. Higher means closer in meaning. Solr reports KNN scores as \((1 + \cos)/2\). |
| **KNN** | k-nearest neighbours: finding the stored embeddings closest to the query's embedding, i.e. the passages closest in meaning. |
| **HNSW** | The graph index Solr uses to find nearest embeddings quickly without comparing against every one. |
| **Hybrid search** | Running keyword (BM25) and meaning (KNN) search together and combining the results. |
| **RRF** | Reciprocal Rank Fusion: combines ranked lists by adding \(1 / (60 + \text{rank})\) from each list, so results found by both rise to the top. See [ADR 0002](decisions/0002-reciprocal-rank-fusion.md). |
| **Relevance floor** | The rule that drops results that are neither a strong keyword match nor close enough in meaning. See [ADR 0003](decisions/0003-relevance-floor.md). |
| **edismax** | Solr's extended DisMax query parser, used for the keyword search across title and text. |
| **Cross-encoder** | A model that reads the query and a passage together to score them. More accurate but slower; optional and off on the live site. |
| **Snippet** | Two or three sentences from a page that best match the query, shown under the result. |

## Pages and storage

| Term | Meaning |
| --- | --- |
| **Chunk** | A passage of up to 150 words from a page. Pages are split into overlapping chunks so each embedding is about one idea. |
| **Page vector** | The average of a page's chunk embeddings. Used to find related pages. |
| **Normalised URL** | A page's address with `www.`, tracking parameters and fragments removed, so the same page saved twice is one entry. |
| **Page id** | The first 32 characters of a SHA-256 hash of the user id and the normalised URL. |
| **Library** | One person's saved pages, identified by a `user_id`. |
| **trafilatura** | The Python library that extracts a page's main text and drops menus, footers and ads. |
| **Solr core** | One Solr index with its own schema. MemoryLane uses one core, `memorylane_v2`, for every user. |

## Sign-in and security

| Term | Meaning |
| --- | --- |
| **Amazon Cognito** | The AWS service that runs sign-in (Google or email) and issues tokens. |
| **Access token** | A short-lived signed token (a **JWT**) that the web app and extension send with every API request. |
| **Refresh token** | A longer-lived token used to get a new access token without signing in again. |
| **`sub`** | The user id inside a Cognito token. MemoryLane's `user_id` comes from it. |
| **PKCE** | Proof Key for Code Exchange: protects the sign-in code, so only the app that started the sign-in can turn it into tokens. |
| **JWKS** | JSON Web Key Set: the public keys Cognito publishes, used to check a token's signature. |
| **CSP** | Content Security Policy: browser rules limiting which scripts and connections a page may use. |
| **HSTS** | HTTP Strict Transport Security: tells browsers to use HTTPS only for this site. |
| **CORS** | Cross-Origin Resource Sharing: browser rules for which websites may call an API. |

## Evaluation

| Term | Meaning |
| --- | --- |
| **MRR@10** | Mean Reciprocal Rank: the average of \(1 / \text{rank}\) of the first relevant result in the top 10. 1.0 means it was always first. |
| **Recall@10** | The share of relevant results found in the top 10. |
| **nDCG@10** | A 0–1 score for how well the top 10 puts relevant results near the top. |
| **SciFact** | A public benchmark of scientific claims and abstracts, used to measure retrieval quality. |

## Documentation

| Term | Meaning |
| --- | --- |
| **ADR** | Architecture Decision Record: a short note of one design choice and its reasons. See [Design Decisions](decisions/index.md). |
| **DFD** | Data Flow Diagram: shows what data moves between processes, data stores and outside entities. See [Data Flow Diagrams](architecture/data-flow.md). |
