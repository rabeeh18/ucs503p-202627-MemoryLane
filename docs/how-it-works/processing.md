# Content Processing

Before it is stored, a saved page is cleaned and split into small passages, and each passage is turned into a vector.

## URL normalisation

The same page can have many URLs. MemoryLane normalises them by:

- Lower-casing the scheme and host
- Removing `www.`
- Removing fragments (`#...`)
- Removing trailing slashes (except the root `/`)
- Removing tracking parameters: `utm_*`, `fbclid`, `gclid`, `ref`, `ref_src`
- Sorting the remaining query parameters

The page id is the first 32 hex characters of `sha256("{user_id}|{normalised_url}")`.

## Cleaning

Raw page text is full of menus, cookie banners, "related articles" lists and footers. MemoryLane runs **trafilatura** on the page's HTML to keep only the main content. If trafilatura finds fewer than 50 words, the text the extension sent is used instead. Either way, citation markers such as `[4]` and junk lines (dividers, table rules, icon rows, lone words) are removed and whitespace is tidied. YouTube transcripts skip trafilatura.

Pages with fewer than **50 words** after cleaning are rejected.

## Chunking

The text is split into paragraphs, then sentences, and packed into chunks:

| Rule | Value |
| --- | --- |
| Largest chunk | 150 words |
| Overlap | each chunk starts with ~30 words of the previous chunk's last sentences |
| Short tail | a last chunk with under 40 new words merges into the one before |
| Long sentences | hard-split by words |

Small, overlapping chunks keep each vector focused on one idea, and the overlap stops an idea being cut in half at a chunk boundary.

## Embeddings

Each chunk is embedded as `title + chunk` with:

```text
BAAI/bge-small-en-v1.5   (384 dimensions, L2-normalised)
```

Queries are embedded with BGE's search instruction (`Represent this sentence for searching relevant passages: `) in front. Passages are embedded without it. `all-MiniLM-L6-v2` can be used instead by changing `EMBEDDING_MODEL` and clearing the prefix.

Embeddings are computed in batches of 32, and the last 1,024 query embeddings are cached.

## Page vector and description

Two more values are computed per page:

- **Page vector**: the normalised mean of the page's chunk vectors. It powers [related pages](../user-guide/map.md#pages) and the [library map](../architecture/map.md).
- **Description**: the page's meta description, otherwise its first readable sentences (up to 300 characters). Snippets fall back to it when no sentence matches the query well.
