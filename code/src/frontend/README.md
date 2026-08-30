# MemoryLane

A semantic webpage memory search frontend, built with Svelte + Tailwind.

## Setup

```bash
npm install
npm run dev
```

The dev server proxies `/api/*` requests to `http://localhost:8000` (see `vite.config.js`) —
point that at your backend, or change the target to match your setup.

## Build

```bash
npm run build
npm run preview
```

## Backend contract

- `POST /api/search`
- Request body: `{ "query": "string" }`
- Response body: `{ "webpages": [{ "url": "string", "title": "string", "timestamp": "ISO 8601" }] }`

Adjust `src/api.js` if your backend's shape differs.

## Structure

```
src/
  App.svelte              main layout, state orchestration
  api.js                  backend calls (search, with timeout + cancellation)
  stores.ts               svelte stores (query, results, loading, error, etc.)
  utils.js                relative-timestamp formatter
  components/
    SearchBar.svelte      centered → sticky search input
    ResultList.svelte     loading / empty / error / results states
    ResultCard.svelte     single result (title, url, relative timestamp)
  styles/
    global.css            Tailwind imports + base dark theme
  main.js                 entry point
```

## Notes on implementation choices

- Rapid re-searches abort the previous in-flight request via `AbortController`,
  so a stale response can never overwrite a newer one.
- A 10s client-side timeout surfaces "Search took too long. Please try again."
  independent of what the backend does.
- All interactive elements (input, buttons, result links) have a visible
  focus outline (`#4a9eff`) for keyboard users.
- Long titles/URLs wrap rather than truncate; URLs use `word-break: break-all`
  as a fallback for unbroken long strings.
