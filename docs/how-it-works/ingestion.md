# Capturing Web Content

The browser extension is the collection layer of MemoryLane.

## Capture process

When a page is eligible for capture, the extension extracts readable content from the page. It can obtain content through the content script and has an injection-based fallback when required.

The extracted data sent to the backend includes:

- URL
- Page title
- Textual content
- Canonical URL when available
- Whether the capture was manual

## Content extraction

The extension works from a clone of the page body and removes elements that generally do not represent the main readable content, including:

- `script`
- `style`
- `noscript`
- `nav`
- `footer`
- `aside`
- `header`
- common navigation, menu, sidebar, and advertisement elements

The resulting text is sent to the backend for further processing.

## Duplicate prevention

The extension keeps track of recently captured URLs and captures currently in progress. This prevents repeated submissions for the same URL in a short period.

The backend also checks whether the normalized webpage already exists before indexing it.

## Backend ingestion

The `/memory` endpoint then:

1. Validates the URL.
2. Normalizes the URL.
3. Generates a deterministic webpage identifier.
4. Checks for an existing webpage.
5. Handles YouTube videos when applicable.
6. Validates the content.
7. Chunks the content.
8. Generates embeddings.
9. Removes outdated chunks for the same webpage when needed.
10. Stores the resulting chunks and metadata in Solr.
