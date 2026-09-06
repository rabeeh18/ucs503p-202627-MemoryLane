# Testing

MemoryLane includes automated tests for important backend behaviors.

## Test areas

The current test suite covers areas including:

- URL normalization
- Chunking behavior
- Retrieval behavior
- API behavior

Representative test files are:

```text
tests/
├── test_api.py
├── test_chunking.py
├── test_retrieval.py
└── test_url_normalization.py
```

## What the tests protect

URL tests verify normalization and deterministic webpage identifiers.

Chunking tests verify that text is divided according to the configured rules.

Retrieval tests cover score normalization, score fusion, and webpage grouping.

API tests cover backend endpoint behavior.

## Evaluation

The repository also contains a retrieval evaluation pipeline under `evaluation/`. It evaluates BM25-only, vector-only, and combined retrieval configurations using retrieval metrics.

The evaluation is separate from the normal automated unit tests.
