# Storing Memories

Apache Solr is the storage and search engine used by MemoryLane.

The project runs an Apache Solr 9.7 instance with a `memorylane` core.

## Why Solr?

Solr provides the search infrastructure needed by MemoryLane in one system. It supports the textual search, dense-vector search, indexing, and document management required by the application.

## Document model

MemoryLane stores individual chunks as Solr documents.

Each document contains information including:

| Field | Purpose |
| --- | --- |
| `id` | Unique chunk document identifier |
| `webpage_id` | Associates chunks with one webpage |
| `url` | Normalized webpage URL |
| `domain` | Webpage domain |
| `title` | Page title |
| `text` | Chunk text |
| `chunk_id` | Position of the chunk |
| `total_chunks` | Number of chunks for the webpage |
| `timestamp` | Storage timestamp |
| `embedding` | 384-dimensional dense vector |

The Solr schema uses a dense vector field for the stored embeddings.

## Webpage identity

The `webpage_id` is derived deterministically from the normalized URL. This lets the system manage all chunks belonging to one webpage as a single logical memory.

When a webpage is reprocessed, older chunks associated with that webpage can be removed before the new chunks are stored.
