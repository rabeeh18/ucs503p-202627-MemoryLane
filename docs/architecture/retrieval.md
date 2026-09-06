# Retrieval Architecture

MemoryLane supports two complementary forms of retrieval:

1. **Lexical retrieval** for words and terminology that directly match stored content.
2. **Semantic retrieval** for content that is conceptually related even when different words are used.

## Lexical retrieval

Solr's eDisMax query mechanism searches the `text` field and gives the `title` field additional importance.

BM25 provides the lexical relevance score.

```text
Query
  ↓
Solr eDisMax
  ↓
text + title
  ↓
BM25 candidates
```

## Semantic retrieval

The search query is converted into the same 384-dimensional embedding space used for stored chunks.

Solr then performs K-nearest-neighbour retrieval over the dense vectors.

```text
Query
  ↓
all-MiniLM-L6-v2
  ↓
384-dimensional vector
  ↓
Solr KNN
```

## Candidate generation

The current configuration retrieves up to 30 candidates from each retrieval source.

## Combining scores

For the production search configuration, the two score lists are normalized independently using min-max normalization.

For a score \(s_i\):

\[
s_i' =
\frac{s_i-s_{\min}}
{s_{\max}-s_{\min}}
\]

The normalized scores are then combined using the configured weights:

\[
S =
0.5S_{\mathrm{BM25}}
+
0.5S_{\mathrm{vector}}
\]

A document that appears in only one source receives zero for the missing source.

## Webpage-level ranking

Retrieval happens at chunk level, but users should not see the same webpage repeatedly.

MemoryLane groups candidates using `webpage_id`. The highest-scoring chunk represents each webpage, and those webpage-level results are returned to the frontend.

```text
Chunk retrieval
      ↓
Webpage grouping
      ↓
Best chunk per webpage
      ↓
Webpage ranking
      ↓
Final results
```
