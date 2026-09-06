# Project Structure

The repository contains the application, browser extension, evaluation code, tests, documentation, and project materials.

## Relevant application structure

```text
code/
└── src/
    ├── backend/
    ├── extension/
    ├── frontend/
    ├── evaluation/
    ├── tests/
    ├── solr/
    ├── scripts/
    ├── docker-compose.yml
    └── requirements.txt
```

## Backend

```text
backend/
├── main.py
├── models.py
├── config.py
├── page_filter.py
├── url_utils.py
├── chunking.py
├── embeddings.py
├── retrieval.py
├── solr_client.py
├── summarizer.py
└── youtube_utils.py
```

## Extension

```text
extension/
├── background.js
├── content.js
├── page_filter.js
├── manifest.json
├── popup.html
├── popup.js
└── popup.css
```

The background service coordinates capture, while the content script extracts readable page content. The page-filter logic is also applied client-side for automatic capture.

## Frontend

The Svelte frontend is located under `code/src/frontend`.

Its main components include the application shell, search bar, result list, result card, API helper, stores, utilities, and global styles.

## Evaluation and tests

Evaluation scripts and data are under `code/src/evaluation`, while automated tests are under `code/src/tests`.
