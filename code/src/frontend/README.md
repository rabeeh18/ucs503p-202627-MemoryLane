# MemoryLane web app

Svelte 4 + Vite. Signed-out visitors see the landing page; signed-in users search their saved pages, browse the library, and export or delete their data.

## Setup

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api -> http://127.0.0.1:8000
npm run build      # static files in dist/
npm run check      # svelte-check
npm test           # vitest (lib/*.test.js)
```

Configuration comes from `VITE_*` variables in the project-root `.env` (`envDir: '..'` in `vite.config.js`):

| Variable | Example |
|---|---|
| `VITE_COGNITO_DOMAIN` | `https://<prefix>.auth.ap-south-1.amazoncognito.com` |
| `VITE_COGNITO_CLIENT_ID` | the Cognito app client id |
| `VITE_REDIRECT_URI` | `http://localhost:5173/auth/callback` locally |
| `VITE_LOGOUT_URI` | `http://localhost:5173/` locally |
| `VITE_API_BASE` | `/api` |

## Structure

```
src/
  main.js              fonts, tokens.css, mounts App
  App.svelte           auth gate + router (/, /library, /auth/callback, /privacy)
  auth.js              Cognito authorization code + PKCE, token refresh, sign-out
  api.js               fetch wrapper: Bearer token, 401 -> refresh once -> retry -> signed out
  stores.ts            query, results, recent pages, loading and error state
  styles/tokens.css    design tokens; no colours outside this file
  lib/                 time.js (relative times), highlight.js (snippet emphasis), router.js
  routes/              Landing, Home, Results, Library, Callback, Privacy
  components/          Header, AccountMenu, SearchBar, ResultRow, PageRow, Kbd, LetterTile,
                       EmptyState, ConfirmDialog
```

The app never renders HTML from the server (`{@html}` is not used anywhere).
