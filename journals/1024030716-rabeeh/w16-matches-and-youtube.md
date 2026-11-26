# Week 16: Better Matches and YouTube in the Browser

*9 – 15 Nov 2026*

## What I did

Stopped weak keyword matches from showing, added in-app problem reports, moved YouTube transcript fetching into the browser, and redesigned the search bar for phones and the home page.

## Problem

Searching "greatest football player of all time" returned the Nintendo article ("the greatest games of all time"): BM25 accepts a page that shares any word. Separately, YouTube had started blocking transcript requests from our server, so videos could not be saved.

## Fix

A keyword match is kept only if it holds most (75%) of the query's words, or is also close in meaning. For videos, the extension fetches the captions inside the user's own YouTube tab and sends them with the save (ADR 0006).

## Learned

Ranking bugs are best described by one concrete bad result. The Nintendo example became a test.
