# Features

## Browser extension

The Chrome extension saves the current page with **Remember this page**, and lets you undo a save straight away. Automatic capture is optional and off by default, and you can exclude any site from it. `Alt+Shift+M` opens the MemoryLane website.

[More on saving pages](user-guide/automatic-capture.md)

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

## Library and library map

The library lists every saved page, newest first, and you can delete pages with undo. The map groups your pages into named topics. From the map you can open a page, see its related pages, or search within one topic.

[More on the library](user-guide/library.md) · [More on the map](user-guide/map.md)

---

## Summaries

Each search result has a **Summarise** button that asks Gemini for a short summary of that page.

---

## Accounts and privacy

You sign in with Google or with email (Amazon Cognito). Every page belongs to one account, and every search, summary and listing sees only your own pages. You can export or delete all your data from the account menu.

[More on privacy](privacy.md)
