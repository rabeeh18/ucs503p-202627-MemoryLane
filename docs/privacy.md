# Privacy

MemoryLane holds personal browsing information, so privacy is part of the design rather than an add-on.

## Accounts and isolation

- You sign in with Google or with email through Amazon Cognito. MemoryLane never sees your password.
- The backend takes your user id from the verified access token (its `sub` claim). No endpoint accepts a user id from the browser.
- **Google and email sign-ins for the same address share one library.** The first time a sign-in is used, the backend asks Cognito for its email, using your own access token. If the email is verified (or the sign-in is through Google), it's linked to the library that address already has. An unverified email is never linked, so signing up with someone else's address doesn't reach their pages.
- To do this, the server keeps your email address and your sign-in ids in a small database next to Solr. **Delete all** removes them along with your pages.
- Every read, write, search, summary and delete in Solr is filtered by that user id. A page id is derived from your user id and the URL, so two people saving the same page get separate copies.
- Asking for another person's page returns `404`, the same as a page that doesn't exist.

## Where pages are kept

With the browser extension, pages are kept **on your device** by default: saved, stored and searched in your browser, never sent to the server ([Pages on Your Device](how-it-works/local-search.md)).

- The browser's copy is **encrypted**, one record per page, with a device key the server gives after you sign in. The extension keeps that key in memory and forgets it when you sign out, so a signed-out browser profile can't read your pages. The server has the key but never the pages.
- You can choose the server instead (Settings in the extension), and past a size limit you set, the oldest device pages can move to the server, after you agree.
- **Encrypted backups** of the device's pages are locked with a recovery key that only you have. The server stores them and can't open them; without the key, nobody can.
- For a page on the device, **Summarise** sends that page's text to the server for that one summary; it is not stored or logged.

## What is stored

For each page you save: its URL, title, cleaned text, a short description, the time you saved it, and the embeddings used for search and related pages.

Pages kept on the server live in Solr on the MemoryLane server (AWS, Mumbai region). The server's logs record page ids, not the URLs you save. Solr is bound to the server's localhost and is not reachable from the internet; only Caddy (HTTPS) is public.

## Automatic capture

Automatic capture is **off by default**. It only runs when you're signed in and have turned it on in the extension. Even then, the extension skips:

- Social-media sites
- Banks and payment services
- Email: Gmail, Outlook, Yahoo Mail, Proton Mail, iCloud Mail and other webmail
- Private apps (Google Docs and Drive, Teams, Notion, Slack, WhatsApp Web, college systems and similar), local and intranet addresses, account areas of any site, and links carrying a secret
- Pages that don't read like content: with a visible password field, a compose box or editor, mostly a form, or marked `noindex`
- Pages you didn't stay on: a page is only saved after 30 seconds in view, or once you've scrolled halfway
- Login, sign-up, account, password, checkout, billing, payment and wallet pages
- Browser-internal pages (`chrome://`, extensions, `file://`, ...)
- Search-engine result pages
- Utility pages such as error, privacy, terms, cookie and sitemap pages
- Files such as PDFs, images, media, archives, CSV, JSON and XML
- Any site you add to **Excluded sites** in the extension
- MemoryLane's own website

The filtering happens in the extension, before anything is sent. The server checks the address rules again for every automatic save, so an outdated extension can't store these pages either. The popup's **Auto-saved today** list shows what was saved automatically, with one-click removal.

## YouTube videos

When you save a YouTube video, the extension asks YouTube, from inside the YouTube tab you're on, for that video's captions, title, description and length, and sends them to MemoryLane with the page. It contacts only youtube.com, sends no cookies, and does this only for the video you are saving.

## What is sent to Google Gemini

Gemini is optional. When the server has a Gemini key:

- **Summaries:** the text of one page is sent when you press **Summarise** on that result.

Without a key, summaries are turned off.

Apart from Gemini summaries, the only thing that leaves the server is a problem report you choose to send, emailed through Amazon SES (below).

## Problem reports

**Report a problem** (in the account menu on the website, and in the extension) sends your message to the maintainer by email, through Amazon SES. The form lists everything that goes with it before you send:

- your account email, so you can get a reply;
- whether it came from the website or the extension, and its version;
- the page you were on, as a path only (`/search`, never the search terms);
- your browser (its user-agent string);
- the last error message the app showed, if any.

Your saved pages and searches are not included. Reports are kept in a small database on the server (so none are lost if email is briefly down); **Delete all my data** removes them.

## Deleting your data

From the account menu (top right of the website), **Delete all my data** removes all your pages from the index, your sign-in links and your problem reports.

Single pages can be deleted from the library or search results, with a few seconds to undo.
