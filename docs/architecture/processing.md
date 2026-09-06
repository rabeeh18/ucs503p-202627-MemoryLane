# Processing Architecture

MemoryLane's processing pipeline turns captured browser content into searchable memory.

## Pipeline

```text
Captured content
      ↓
URL validation
      ↓
URL normalization
      ↓
Webpage ID generation
      ↓
Content validation
      ↓
YouTube transcript handling (when applicable)
      ↓
Chunking
      ↓
Embedding generation
      ↓
Solr indexing
```

## URL identity

The normalized URL is used to generate a deterministic webpage identifier. This identifier is the link between all chunks belonging to one logical webpage.

## Normal webpage content

For ordinary pages, extracted text is validated and then divided into chunks before embeddings are generated.

## YouTube content

For supported YouTube URLs, the backend retrieves an available transcript and uses the resulting text as the content to be chunked and embedded.

## Re-indexing

If an existing webpage needs to be replaced, the backend can remove the old chunks associated with its webpage identifier before storing the new representation.
