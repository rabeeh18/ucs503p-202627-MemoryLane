# 0012. Keep pages on the device by default, with the server as a fallback

**Status:** Accepted · **Date:** November 2026

## Context

A record of everything a person reads is about as personal as data gets. Until now every saved page was stored and searched on the server, so the server, and whoever runs it, could read every library. Browsers keep history on the device for the same reason.

The supervisor's guidance was to offer both: let people choose by how comfortable they are with their data, and fall back to the server for large libraries, with the limit a user setting and sensible defaults.

## Decision

The extension keeps pages **on the device by default**: saved, stored (encrypted, [0016](0016-encrypt-local-pages-and-backups.md)) and searched in the browser. The server version stays as it was and is the fallback:

- **Choice:** in the extension's settings, new pages go to **this device** or **the server**.
- **Size limit:** a limit in megabytes (default 100 MB, about 5,000 to 8,000 typical pages). Past it, the **oldest** pages move to the server, after the user agrees once (or never, if they say so).
- **One place per page:** a page lives whole on the device or on the server, never split.
- **Search covers both:** the website asks the extension for this device's results and the server for its own, and fuses the two ranked lists with Reciprocal Rank Fusion (k = 60). With every page in one place, the result is that place's ranking exactly.
- **Same search everywhere:** the browser engine reproduces the server's search exactly ([0013](0013-exact-vector-search.md), [0014](0014-own-bm25-no-orama.md), [0015](0015-server-code-in-the-browser.md)): on the parity set, 117 of 117 queries return the same pages, order and snippets.
- Sign-in is still required. It identifies the library, gives the device key, and enables summaries and encrypted backups.

## Alternatives

| Option | Why not |
| --- | --- |
| Keep server-only storage | The server can read every page; the strongest privacy answer is not to hold them |
| Local only, no server | No phone access, no safety if the browser is wiped, no help for very large libraries |
| Split each library by page type or size | Every search, delete and listing would have to touch both places for no gain |
| Move new saves (not the oldest) past the limit | The newest pages are searched most; keeping them local keeps them fastest |
| Orama or another JS search library | Slower and far heavier in the project's tests ([0014](0014-own-bm25-no-orama.md)) |

## Consequences

- **Easier:** by default the server never receives a saved page. The privacy statement becomes "we don't have your pages" rather than "we isolate them".
- **Harder:** pages on the device are searchable only in that browser profile (not on a phone, or in another browser) unless they are moved to the server. The extension grows to ~16 MB zipped, and the model (~130 MB) is downloaded once. Saving takes a few seconds per long page in the browser.
- Two engines must stay identical: the parity checks in `code/src/evaluation/parity/` compare them on keyword scores, full searches and saved pages.
