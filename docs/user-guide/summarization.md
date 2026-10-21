# Summaries

Each search result, and each page selected on the map, has a **Summarise** button. It asks Google Gemini for a short summary of that one page.

```text
Summarise
   ↓
POST /api/summarize {query, id}
   ↓
Load the page's stored text (your pages only)
   ↓
Gemini
   ↓
Summary shown under the result
```

## What Gemini sees

Only the stored text of the page you chose (long pages are truncated), and your query. Gemini is asked to summarise that text only, without adding outside knowledge.

## Length

The wording of your query sets the length:

- **Short** (1–2 sentences): words like *brief*, *quick summary*, *tl;dr*, *in a nutshell*
- **Long** (2–3 short paragraphs): words like *detailed*, *in-depth*, *comprehensive*, *explain fully*
- **Medium** otherwise

## When it's unavailable

Summaries need a Gemini key on the server. Without one, or if Gemini fails, the result shows a short message instead, and search keeps working. `GET /health` reports whether Gemini is available.
