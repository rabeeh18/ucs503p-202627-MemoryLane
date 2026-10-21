# Capturing Web Content

The Chrome extension is MemoryLane's collection layer. The server does the cleaning.

## What the extension sends

When you save a page (or auto-capture picks one up), the extension injects `content.js` into the tab, which returns:

- The page's full **HTML**
- Its visible **text** (the fallback if cleaning finds nothing)
- The **canonical URL**, if the page declares one

The service worker posts these, with the URL, title and whether the save was manual, to `POST /api/memory`, using the signed-in user's access token. If the token has expired, the extension refreshes it once and retries.

Auto-capture also checks the page against the [capture rules](../user-guide/automatic-capture.md#what-automatic-capture-skips) and your excluded sites before sending anything, and doesn't send a URL again while a save of it is in progress, or within a minute of auto-capturing it.

## What the backend does

All of this happens in one function, `ingest_page` (`backend/ingest.py`). It is shared by the API, the re-index and backfill scripts and the evaluation.

1. Take the user id from the verified token (never from the request).
2. Prefer the canonical URL, then [normalise](processing.md#url-normalisation) it.
3. Compute `page_id = sha256(user_id | normalised URL)[:32]`.
4. **YouTube**: fetch the transcript and metadata instead of using the page (see [YouTube Videos](../user-guide/youtube.md)).
5. **Other pages**: extract the main text from the HTML with trafilatura. If that fails, use the extension's text.
6. Reject the page with `422` if it has fewer than 50 words.
7. If the page is already stored with the same content hash and embedding model, return `unchanged` and do nothing.
8. Chunk, embed, compute the page vector and description.
9. Upsert the chunks as `{page_id}::{n}`, then delete any higher-numbered chunks left from an older, longer version.
10. Clear the user's cached library map.

The response is `{status: saved | unchanged | skipped, message, page}`.

## Duplicates

Because `page_id` is derived from the normalised URL, the same page saved twice (with or without `www.`, tracking parameters or a fragment) updates one entry instead of creating two. Different users saving the same URL get separate entries.
