# Week 4: The First Working Model

*17 – 23 Aug 2026*

## What I did

At our first meeting with Sir on 17 Aug, we laid out the project's flow: capture each page as it is visited, embed its content, store it in a vector database, and answer a plain-language query with the most relevant URL. The deliverable was a working model within three days. I made my first commit the same day, a small test to learn the team's Git workflow. Two days later, Rabeeh and I had the first working prototype, and I committed its code: a FastAPI backend that embeds each saved page with `all-MiniLM-L6-v2` and stores it in ChromaDB, and a Tampermonkey userscript that extracts the article with Mozilla Readability and sends it to the backend. I announced the working model on the forum, listing what it delivered and the design choices behind it.

## Problem

The userscript runs on every page, so it would happily save login screens and account pages, and pages built by JavaScript were often captured before their content had loaded. Revisiting a page also saved it again.

## Fix

The script waits 7 seconds before extracting, so dynamic pages have time to load. A weighted check looks for password fields, login forms, login-like URL paths and short "log in" buttons, so a page that only *mentions* the word "login" is not blocked. The same URL is not saved again within 30 minutes.

## Learned

A quick prototype (Tampermonkey instead of our own extension) let us test the core idea in days, and the forum discussion that followed shaped the next weeks: Sir questioned storing full text against using snapshots, pointed out that LLM calls are expensive, and suggested Apache Solr.

## Forum

- [MemoryLane: Overview of the meeting](https://tiet-ucs503.bvraghav.com/d/23-memorylane--overview-of-the-meeting/1) (17 Aug): the project flow and the three-day deliverable, posted by Rabeeh
- [Working Model Update](https://tiet-ucs503.bvraghav.com/d/45-working-model-update-memorylane/1) (19 Aug): my announcement of the working model, its deliverables and design choices, and the discussion with Sir that followed
