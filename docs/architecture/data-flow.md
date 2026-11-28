# Data Flow Diagrams

These diagrams show what data moves between MemoryLane and the outside world, and between its main processes. Processes are circles, data stores are cylinders, and external entities are rectangles.

## Level 0: context diagram

The whole system as one process, with everything it exchanges data with.

```mermaid
flowchart LR
    user["User<br/>(browser + extension)"]
    cognito["Amazon Cognito"]
    youtube["YouTube"]
    gemini["Google Gemini"]
    ses["Amazon SES"]
    admin["Maintainer"]

    ml(("0<br/>MemoryLane"))

    user -- "pages, queries, requests, reports" --> ml
    ml -- "results, summaries, lists" --> user
    youtube -- "captions + video details" --> ml
    ml -- "access token" --> cognito
    cognito -- "email, verified" --> ml
    ml -- "page text + query" --> gemini
    gemini -- "summary" --> ml
    ml -- "report email" --> ses
    ses -- "report email" --> admin
```

The user signs in with Amazon Cognito directly, and sends its access token with every request; that exchange is between two external entities, so it isn't drawn here (see [Security](security.md#sign-in-and-the-first-request)).

YouTube data is fetched by the extension inside the user's YouTube tab, so it reaches the server as part of the save request. The server contacts YouTube itself only when an older extension sent nothing.

## Level 1: main processes

Level 1 opens the system into six processes and four data stores (D4 is the encrypted store in the browser, for pages kept on the device). It's drawn in two halves so the lines stay readable. A two-headed arrow is a request and its answer, labelled *request / answer*.

### Saving and finding pages

```mermaid
flowchart TB
    user["User"]
    youtube["YouTube"]
    cognito["Amazon Cognito"]
    gemini["Google Gemini"]

    p1(("1.0<br/>Authenticate"))
    p2(("2.0<br/>Save page"))
    p3(("3.0<br/>Search"))
    p4(("4.0<br/>Summarise"))

    d1[("D1 accounts.db<br/>sign-in links")]
    d2[("D2 Solr<br/>chunks, vectors, metadata")]
    d4[("D4 Device store<br/>IndexedDB, encrypted")]

    user -->|"access token"| p1
    p1 <-->|"token / email, verified"| cognito
    p1 <-->|"sub / library, device key"| d1

    user <-->|"page / saved status"| p2
    youtube -->|"captions + details"| p2
    p2 -->|"chunks, embeddings (default)"| d4
    p2 -->|"chunks, embeddings (server)"| d2
    d4 -->|"oldest pages past the limit"| d2

    user <-->|"query / ranked pages + snippets"| p3
    d4 -->|"BM25 + vector matches"| p3
    d2 -->|"BM25 + vector matches"| p3

    user <-->|"page id / summary"| p4
    d4 -->|"page text"| p4
    d2 -->|"page text"| p4
    p4 <-->|"text + query / summary"| gemini
```

### Library, account and reports

```mermaid
flowchart LR
    user["User"]
    ses["Amazon SES"]

    p5(("5.0<br/>Manage library"))
    p6(("6.0<br/>Report a<br/>problem"))

    d1[("D1 accounts.db<br/>sign-in links")]
    d2[("D2 Solr<br/>chunks, vectors, metadata")]
    d3[("D3 reports.db<br/>problem reports")]
    d4[("D4 Device store<br/>IndexedDB, encrypted")]

    user <-->|"list, delete, delete all /<br/>pages"| p5
    p5 <-->|"pages"| d2
    p5 <-->|"pages on the device"| d4
    p5 -->|"delete links"| d1
    p5 <-->|"user's reports"| d3

    user -->|"message + context"| p6
    p6 <-->|"report / unsent reports"| d3
    p6 -->|"email"| ses
```

Processes 2.0 to 6.0 all get the `user_id` from 1.0 Authenticate; those arrows are left out to keep the diagrams readable.

| Process | Code | What it does |
| --- | --- | --- |
| 1.0 Authenticate | `backend/auth.py`, `backend/accounts.py` | Verifies the token; maps the sign-in to its library, linking Google and email sign-ins with the same verified email |
| 2.0 Save page | `extension/background.js`, `backend/ingest.py` (also run in the extension by `extension/engine/`) | Captures the page (or a video's captions), cleans, chunks, embeds and stores it: on the device (D4) by default, or on the server (D2) |
| 3.0 Search | `backend/retrieval.py`, `backend/query_intent.py`, `backend/snippets.py`; `extension/engine/retrieval.js` for D4 | Hybrid BM25 + vector search, fusion, relevance floor, snippets; the website fuses device and server results |
| 4.0 Summarise | `backend/summarizer.py` | Sends one page's stored text to Gemini |
| 5.0 Manage library | `backend/main.py` | Lists pages, deletes one, and deletes everything |
| 6.0 Report a problem | `backend/reports.py` | Stores the report, then emails it in the background with retries |

Every process gets the `user_id` from 1.0, and every read or write of D2 is filtered by it (see [Security](security.md)).
