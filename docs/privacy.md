# Privacy

MemoryLane holds personal browsing information, so privacy is part of the design rather than an add-on.

## Accounts and isolation

- You sign in with Google or with email through Amazon Cognito. MemoryLane never sees your password.
- The backend takes your user id from the verified access token (its `sub` claim). No endpoint accepts a user id from the browser.
- Every read, write, search, summary, map and delete in Solr is filtered by that user id. A page id is derived from your user id and the URL, so two people saving the same page get separate copies.
- Asking for another person's page returns `404`, the same as a page that doesn't exist.

## What is stored

For each page you save: its URL, title, cleaned text, a short description, the time you saved it, and the embeddings used for search and for the map.

The data lives in Solr on the MemoryLane server (AWS, Mumbai region). Solr is bound to the server's localhost and is not reachable from the internet; only Caddy (HTTPS) is public.

## Automatic capture

Automatic capture is **off by default**. It only runs when you're signed in and have turned it on in the extension. Even then, the extension skips:

- Social-media sites
- Banks and payment services
- Login, sign-up, account, password, checkout, billing, payment and wallet pages
- Browser-internal pages (`chrome://`, extensions, `file://`, ...)
- Search-engine result pages
- Utility pages such as error, privacy, terms, cookie and sitemap pages
- Files such as PDFs, images, media, archives, CSV, JSON and XML
- Any site you add to **Excluded sites** in the extension
- MemoryLane's own website

The filtering happens in the extension, before anything is sent.

## What is sent to Google Gemini

Gemini is optional. When the server has a Gemini key:

- **Summaries:** the text of one page is sent when you press **Summarise** on that result.
- **Map topic names:** when your map is built, the titles of a sample of pages in each topic (and a few keywords) are sent once so the topics get readable names. Names are cached, so this only happens again when a topic's pages change.

Without a key, summaries are turned off and the map names topics from their keywords instead. Nothing else leaves the server.

## Export or delete

From the account menu (top right of the website):

- **Export my data** downloads every page you saved as JSON.
- **Delete all my data** removes all your pages from the index.

Single pages can be deleted from the library, search results or the map, with a few seconds to undo.
