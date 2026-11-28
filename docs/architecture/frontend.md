# Frontend and Extension

## Web app

The web app is built with **Svelte 4** and **Vite**, in `code/src/frontend`. It has no UI framework: colours, type (IBM Plex Sans and Mono) and spacing come from design tokens in `styles/tokens.css`, in a monochrome dark theme.

```text
frontend/src/
├── App.svelte            Routing: signed-out landing vs. the app
├── auth.js               Cognito PKCE sign-in, token refresh, sign-out
├── api.js                Authenticated fetch; 401 → refresh once → retry
├── stores.ts             Shared state (recent pages, query, ...)
├── pageDeletes.js        Delete-with-undo queue
├── routes/
│   ├── Landing.svelte    Signed-out home
│   ├── Home.svelte       Search box + recently saved
│   ├── Results.svelte    Results, snippets, summaries
│   ├── Library.svelte    All saved pages
│   ├── Extension.svelte  Extension download and install steps
│   ├── Privacy.svelte
│   └── Callback.svelte   Sign-in redirect
├── components/
│   ├── Header, SearchBar (with voice), ResultRow, PageRow, LetterTile,
│   └── AccountMenu, ConfirmDialog, Toasts, ScrollPill, EmptyState, ...
└── lib/                  router, highlight, time, domain, deletes, greetings
```

### Notes

- **Routing** is a small history-based router in `lib/router.js`. Caddy serves `index.html` for every path.
- **Sign-in**: the access token is kept in memory only. The refresh token is in `localStorage`, so a reload stays signed in. Because of that, the app never renders user-supplied HTML, and Caddy sends a strict Content Security Policy.
- **Native scrollbars are hidden**; a small floating pill shows the scroll position.
- In development, Vite proxies `/api` to `http://127.0.0.1:8000`.

## Extension

The extension is Manifest V3, in `code/src/extension`, written as plain ES modules.

| File | Role |
| --- | --- |
| `background.js` | Service worker: sign-in, save (to this device or the server), undo, auto-capture, excluded sites, `Alt+Shift+M`, the website's requests, idle and backup alarms |
| `local.js` | Local-first storage: opens the engine for the signed-in library, saves locally, moves the oldest pages to the server past the size limit, encrypted backups |
| `engine.html`, `engine/host.js` | Offscreen document hosting the local engine (model, Pyodide, index) |
| `engine/` | The local search engine: `analyzer.js`, `porter.js`, `bm25.js` (Solr's keyword scoring), `local_index.js`, `retrieval.js`, `query_intent.js`, `snippets.js`, `url.js` (ports of the server's), `ingest.js` + `py/local_ingest.py` (the server's saving code in Pyodide), `embedder.js` (transformers.js), `store.js` and `crypto.js` (encrypted IndexedDB), `core.js` |
| `tools/vendor.mjs` | Build step: bundles Pyodide, the Python packages, the backend's saving modules and transformers.js into `vendor/` |
| `auth.js` | Cognito PKCE through `chrome.identity.launchWebAuthFlow`; tokens in `chrome.storage.local` |
| `api.js` | Authenticated fetch with one refresh-and-retry |
| `content.js` | Injected on demand; returns the page's HTML, text, canonical URL and measurements for auto-capture (words, links, password fields, editors, `noindex`) |
| `engagement.js` | Injected when auto-capture is on; reports once the page has been read (30 s in view, or scrolled halfway) |
| `page_filter.js` | Auto-capture rules (private addresses, `assessContent` for what's on the page), saveable pages, excluded-site matching |
| `site_marker.js` | Runs only on memorylane.site; tells the site the extension is installed and its id |
| `popup.*`, `options.*`, `options_storage.js` | The popup (with **Auto-saved today** and the size-limit prompt) and Settings (storage, backups, excluded sites) |
| `config.js` | Website, API and Cognito endpoints |

The extension's ID is fixed by the public `key` in `manifest.json` (`igdbkkmpnplmboeccgigbjgoefecdhck`), so its Cognito redirect URL is the same on every machine, and the website can message it (`externally_connectable`) for pages kept on the device. See [Pages on Your Device](../how-it-works/local-search.md).
