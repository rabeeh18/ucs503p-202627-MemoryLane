# MemoryLane extension (Chrome, Manifest V3)

Capture-only: the popup saves the current page; searching happens on the website.

## Install (unpacked)

1. `chrome://extensions` → turn on **Developer mode** → **Load unpacked** → choose this `extension/` folder.
2. The extension ID is pinned by the `key` in `manifest.json`:

   **`igdbkkmpnplmboeccgigbjgoefecdhck`**

   Its sign-in redirect URL is `https://igdbkkmpnplmboeccgigbjgoefecdhck.chromiumapp.org/`, which must be in the Cognito app client's allowed callback URLs.

The matching private key is **not** in the repo (it's in `code/src/.secrets/`, which is gitignored). Keep a backup: it's only needed to pack a `.crx`, or to keep this ID on a first Chrome Web Store upload (put it in the zip as `key.pem`).

## Configuration

`config.js` is the only place with endpoints: `WEB_APP_URL`, `API_BASE`, `COGNITO_DOMAIN`, `COGNITO_CLIENT_ID`. For local testing point `WEB_APP_URL` at your dev host and reload the extension.

## Files

| File | Role |
|---|---|
| `background.js` | Service worker (ES module): sign-in, save, undo, auto-capture, excluded sites, `Alt+Shift+M` → website |
| `auth.js` | Cognito PKCE via `chrome.identity.launchWebAuthFlow`; tokens in `chrome.storage.local`; refresh when under 60 s remain |
| `api.js` | Bearer-token fetch; 401 → refresh once → retry → signed out |
| `content.js` | Injected on demand; returns `{html, text, canonicalUrl}` |
| `page_filter.js` | Auto-capture eligibility, saveable pages, host normalisation and exclusions |
| `popup.*` | Popup UI (380px) |
| `options.*` | Excluded sites page |
| `tokens.css`, `fonts/` | Shared design tokens and bundled IBM Plex fonts (SIL OFL, see `fonts/LICENSE-OFL.txt`) |

Auto-capture is off by default. It runs only when signed in, switched on, the page passes `page_filter.js`, and the site isn't excluded. Signing out stops it.
