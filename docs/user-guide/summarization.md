# Summaries

Each search result has a **Summarise** button. It asks Google Gemini for a short summary of that one page.

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

If a page contains instructions meant for the AI ("ignore your rules and …"), they are treated as page text, not commands. A summary never contains a link that isn't on the page itself, and it's shown as plain text. See [Security](../architecture/security.md#prompt-injection-summaries) for how this works.

## Length

The wording of your query sets the length:

- **Short** (1–2 sentences): words like *brief*, *quick summary*, *tl;dr*, *in a nutshell*
- **Long** (2–3 short paragraphs): words like *detailed*, *in-depth*, *comprehensive*, *explain fully*
- **Medium** otherwise

## When it's unavailable

Summaries need a Gemini key on the server. Without one, or if Gemini fails, the result shows a short message instead, and search keeps working. `GET /health` reports whether Gemini is available.
