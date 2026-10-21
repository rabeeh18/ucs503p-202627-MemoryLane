# Processing Architecture

Every page enters MemoryLane through one function, `ingest_page(user_id, url, title, content, html, canonical_url, is_manual)` in `backend/ingest.py`. The API, `scripts/reindex.py`, `scripts/backfill_page_vectors.py` and the evaluation scripts all call it, so a page is processed the same way whichever path it came in by.

## Pipeline

```text
Request (url, title, content, html?, canonical_url?, is_manual)
      ↓
Canonical URL preferred → normalise → page_id = sha256(user_id|url)[:32]
      ↓
YouTube? ── yes ─▶ transcript + metadata (built from the video id)
      │ no
      ▼
trafilatura on html (fallback: content) → tidy
      ↓
< 50 words? → 422
      ↓
Same content_hash and embedding_model as stored? → "unchanged"
      ↓
Chunk → embed "title + chunk" → page vector = normalised mean
      ↓
description = meta description or first readable sentences
      ↓
Upsert {page_id}::0..n-1 → delete chunks ≥ n
      ↓
Invalidate the user's library map
```

## Idempotence

- The `content_hash` is a SHA-256 of the cleaned text. Saving an unchanged page costs one Solr lookup.
- If the stored `embedding_model` differs from the current one, the page is re-embedded even when the text is unchanged. Switching models therefore only needs a re-save or re-index, not a schema change.
- Pages stored before `description` existed are re-ingested once, on their next save, to gain it. Pages without a `page_embedding` get one from `scripts/backfill_page_vectors.py`.

## Why the chunk upsert works this way

Solr has no transactions across documents. Writing the new chunks first, then deleting only those numbered past the new count, means a reader always sees a complete version of the page: the old one or the new one, never an empty page.

The backfill never uses Solr atomic updates. Those rewrite the document from its stored fields, and the chunk `embedding` field is not stored, so an atomic update would silently drop it.
