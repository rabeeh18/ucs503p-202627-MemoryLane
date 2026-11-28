# Features

## Browser extension

The Chrome extension saves the current page with **Remember this page**, and lets you undo a save straight away. Automatic capture is optional and off by default. It only saves pages you actually read that look like articles, docs, posts or videos, skips private pages such as email and documents, and lists what it saved today so you can remove anything in one click. You can exclude any site. `Alt+Shift+M` opens the MemoryLane website.

[More on saving pages](user-guide/automatic-capture.md)

---

## Pages on your device

By default the extension keeps your pages in your browser, encrypted, and searches them there: the server never receives them. Search is the same as on the server, down to the order of results. You can keep pages on the server instead, set a size limit past which the oldest move there (after you agree), and make encrypted backups that only your recovery key opens.

[More on storage and backups](user-guide/storage.md)

---

## Content extraction

Each saved page is cleaned with trafilatura, so menus, footers, cookie banners and adverts stay out of your library. YouTube videos are saved through their transcripts.

---

## Hybrid search

Search runs keyword (BM25) and meaning (vector) retrieval together and combines them with Reciprocal Rank Fusion. Each result shows a short snippet of the sentences that best match the query.

Example:

"Find documentation about ROS navigation"

[More on search](user-guide/search.md)

---

## Library

The library lists every saved page, newest first, and you can delete pages with undo.

[More on the library](user-guide/library.md)

---

## Summaries

Each search result has a **Summarise** button that asks Gemini for a short summary of that page.

---

## Problem reports

**Report a problem**, on the website and in the extension, emails a message to the maintainer. The form shows everything that is sent with it.

---

## Accounts and privacy

You sign in with Google or with email (Amazon Cognito). Every page belongs to one account, and every search, summary and listing sees only your own pages. You can delete all your data from the account menu.

[More on privacy](privacy.md)
