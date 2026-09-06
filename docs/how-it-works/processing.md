# Content Processing

MemoryLane transforms captured content into smaller searchable units before storing it.

## URL normalization

URLs can have multiple representations that refer to the same logical resource.

MemoryLane normalizes URLs by handling details such as:

- Scheme and hostname normalization
- Removing the `www` prefix
- Removing default ports
- Removing fragments
- Removing common tracking parameters
- Normalizing trailing slashes
- Sorting query parameters

A deterministic webpage identifier is generated from the normalized URL.

## Validation

Very short or invalid content is not treated as a useful webpage memory.

For ordinary webpages, the extension also avoids sending pages with insufficient extracted text during automatic capture.

## Chunking

Large pages are divided into smaller chunks.

The configured target range is approximately 300–500 words. Paragraph boundaries are used where possible. Oversized paragraphs can be split at sentence boundaries, with further word-based splitting when a single sentence is still too large.

Very small trailing chunks may be merged back into the preceding chunk.

## Embeddings

Each chunk is converted into a dense vector using:

```text
all-MiniLM-L6-v2
```

The model produces a 384-dimensional representation.

The vectors are normalized and used with cosine similarity for dense retrieval.

## Metadata

Chunks retain their relationship to the original webpage through fields such as:

- `webpage_id`
- URL
- Domain
- Title
- Chunk identifier
- Total chunk count
- Timestamp
- Embedding
