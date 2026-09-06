# Backend Architecture

The backend is implemented with FastAPI and is responsible for coordinating MemoryLane's core operations.

## Main modules

```text
backend/
├── main.py
├── models.py
├── config.py
├── url_utils.py
├── page_filter.py
├── chunking.py
├── embeddings.py
├── retrieval.py
├── solr_client.py
├── summarizer.py
└── youtube_utils.py
```

### `main.py`

Defines the FastAPI application and API endpoints. It coordinates memory ingestion, search, health checks, and summarization.

### `models.py`

Defines Pydantic request and response models used by the API.

### `url_utils.py`

Handles URL normalization and deterministic webpage ID generation.

### `page_filter.py`

Contains the URL eligibility rules used for automatic capture.

### `chunking.py`

Converts long text into chunks suitable for embedding and retrieval.

### `embeddings.py`

Loads and uses the Sentence Transformer embedding model.

### `retrieval.py`

Handles candidate retrieval, score normalization, score fusion, and webpage-level aggregation.

### `solr_client.py`

Provides the backend interface to the Solr index.

### `youtube_utils.py`

Provides YouTube URL detection, video-ID handling, and transcript-related utilities.

### `summarizer.py`

Handles optional Gemini-based summarization.

### `config.py`

Contains application and retrieval configuration values.
