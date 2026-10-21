# Frontend and Extension

## Web app

The web app is built with **Svelte 4** and **Vite**, in `code/src/frontend`. It has no UI framework: colours, type (IBM Plex Sans and Mono) and spacing come from design tokens in `styles/tokens.css`, in a monochrome dark theme.

```text
frontend/src/
├── App.svelte            Routing: signed-out landing vs. the app
├── auth.js               Cognito PKCE sign-in, token refresh, sign-out
├── api.js                Authenticated fetch; 401 → refresh once → retry
├── stores.ts             Shared state (recent pages, query, ...)
├── mapStore.js           Loads and caches the library map
├── pageDeletes.js        Delete-with-undo queue
├── routes/
│   ├── Landing.svelte    Signed-out home
│   ├── Home.svelte       Search box + recently saved
│   ├── Results.svelte    Results, snippets, summaries, topic filter
│   ├── Library.svelte    All saved pages
│   ├── MapPage.svelte    Library map + list view
│   ├── Extension.svelte  Extension download and install steps
│   ├── Privacy.svelte
│   └── Callback.svelte   Sign-in redirect
├── components/
│   ├── Header, SearchBar (with voice), ResultRow, PageRow, LetterTile,
│   ├── AccountMenu, ConfirmDialog, Toasts, ScrollPill, EmptyState, ...
│   └── map/              MapCanvas (SVG), MapPanel, MapList, MapSkeleton
└── lib/                  router, highlight, time, domain, deletes, mapView
```

### Notes

- **Routing** is a small history-based router in `lib/router.js`. Caddy serves `index.html` for every path.
- **Sign-in**: the access token is kept in memory only. The refresh token is in `localStorage`, so a reload stays signed in. Because of that, the app never renders user-supplied HTML, and Caddy sends a strict Content Security Policy.
- **Map** drawing is plain SVG in two layers, topics and pages. The geometry (fit, zoom, pan, culling, detail levels) is pure functions in `lib/mapView.js`, unit-tested with vitest.
- **Native scrollbars are hidden**; a small floating pill shows the scroll position.
- In development, Vite proxies `/api` to `http://127.0.0.1:8000`.

## Extension

The extension is Manifest V3, in `code/src/extension`, written as plain ES modules.

| File | Role |
| --- | --- |
| `background.js` | Service worker: sign-in, save, undo, auto-capture, excluded sites, `Alt+Shift+M` |
| `auth.js` | Cognito PKCE through `chrome.identity.launchWebAuthFlow`; tokens in `chrome.storage.local` |
| `api.js` | Authenticated fetch with one refresh-and-retry |
| `content.js` | Injected on demand; returns the page's HTML, text and canonical URL |
| `page_filter.js` | Auto-capture eligibility, saveable pages, excluded-site matching |
| `site_marker.js` | Runs only on memorylane.site; tells the site the extension is installed |
| `popup.*`, `options.*` | The popup and the excluded-sites page |
| `config.js` | Website, API and Cognito endpoints |

The extension's ID is fixed by the public `key` in `manifest.json` (`igdbkkmpnplmboeccgigbjgoefecdhck`), so its Cognito redirect URL is the same on every machine.
