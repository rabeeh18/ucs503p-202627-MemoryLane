# Retrieval Architecture

Search combines two complementary retrievers:

1. **Lexical (BM25)** finds pages that use the query's words, including exact names, codes and jargon.
2. **Semantic (vector KNN)** finds pages about the same idea, even in different words.

Both run over chunks and are restricted to the signed-in user's pages. Their rankings are fused, grouped into pages, filtered for relevance, and given snippets.

```text
Query
  ├─▶ BM25 (edismax on title^2 text)          ─┐
  └─▶ embed query → KNN on chunk embeddings   ─┤  top 50 chunks each, user-filtered
                                               ▼
                         Reciprocal Rank Fusion
                                               ▼
                       (optional) cross-encoder rerank
                                               ▼
                        Group chunks by page_id
                                               ▼
                           Relevance floor
                                               ▼
                       Snippets → top-K pages
```

The BM25 query and the query embedding run concurrently.

## Lexical retrieval

Solr's **edismax** parser searches `title^2 text`, with a phrase boost `pf=text^2 title^3` so pages containing the query as a phrase rank higher. Both fields use `text_en` (possessives, stopwords, Porter stemming), so *learning* matches *learn*. Field queries in user input are disabled (`uf=-*`).

## Semantic retrieval

The query is embedded with `BAAI/bge-small-en-v1.5` (with BGE's search instruction in front) into the same 384-dimensional space as the chunks. Solr runs `{!knn f=embedding topK=50}` with the user filter as a **pre-filter**, so the 50 nearest chunks are all the user's own.

## Reciprocal Rank Fusion

BM25 scores and cosine similarities are on different scales, so MemoryLane fuses **ranks**, not scores. For a chunk \(d\):

\[
\mathrm{RRF}(d) =
\frac{w_{\mathrm{bm25}}}{k + r_{\mathrm{bm25}}(d)}
+
\frac{w_{\mathrm{knn}}}{k + r_{\mathrm{knn}}(d)}
\]

with \(k = 60\) and both weights 1.0. A chunk missing from one list gets nothing from it. Chunks found by both retrievers rise to the top.

!!! note "Earlier versions"
    The first version min-max normalised the two score lists and averaged them (0.5 / 0.5). Min-max depends on the highest and lowest score in each list, so a single outlier changes every other score. RRF uses only ranks and has no such dependence.

## Optional reranking

With `RERANK_ENABLED=true`, the top 20 fused chunks are re-scored by a cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) that reads the query and chunk together. It is off on the live site to save memory.

## Page-level grouping

Users see pages, not chunks. Chunks are grouped by `page_id`, and each page scores:

\[
S_{\mathrm{page}} = s_{\mathrm{best}} + 0.3 \cdot s_{\mathrm{second}}
\]

so a page with two good passages beats a page with one, without long pages winning just by having many chunks.

## Relevance floor

KNN always returns 50 neighbours, however unrelated. A page with **no** BM25 match is dropped unless its best chunk's cosine similarity is at least `MIN_VECTOR_SIMILARITY` (0.55). Solr reports KNN scores as \((1 + \cos)/2\), so the backend converts them first. Pages that match a query word are always kept.

## Snippets

For each result, `backend/snippets.py` picks 2–3 consecutive readable sentences around the sentence that contains the most query terms. Ties are broken by embedding similarity to the query. A readable sentence has 8+ words, is at least 70% letters, has no table pipes and ends in punctuation. Snippets are 200–280 characters. If no sentence qualifies, the page's stored description is used.

## Search within a topic

`POST /search` with a `topic` restricts both retrievers to the page ids in that [library-map](map.md) topic. If the user's map has changed since the topic id was issued, the API returns `409`, and the web app finds the topic again by name.

## Debugging

`"debug": true` adds each page's `bm25_rank`, `knn_rank`, `fused_score`, `vector_similarity` and per-stage `timings` to the response. The CLI prints the same with `--debug`.
