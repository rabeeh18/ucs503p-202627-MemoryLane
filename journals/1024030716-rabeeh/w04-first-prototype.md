# Week 4: Proposal and the First Prototype

*17 – 23 Aug 2026*

## What I did

Wrote and submitted the project proposal (LaTeX), and laid out the project flow at our first meeting with Sir: capture a page, embed it, and answer a plain-language query with the matching URL. Ishan and I built the first working prototype in three days:

- a TamperMonkey userscript that extracted pages with Mozilla Readability;
- a FastAPI backend that embedded the text with `all-MiniLM-L6-v2` and kept vectors and content together in ChromaDB, with no separate database;
- Gemini summaries written per query rather than stored.

At the end of the week I improved the search and added a seed set of URLs with the first evaluation scripts.

## Problem

Every query returned exactly five URLs, however many were relevant, and the backend had to be run separately. Sir also asked why we stored the full page text instead of a snapshot.

## Fix

Full text stays: snapshots aren't reliable on every site, the text gives better query-specific summaries, and storage was not yet a bottleneck. The fixed five results and the userscript went on the list for the next version. `seed_ingest.py` and `evaluate.py` gave a repeatable way to score search, so changes could be compared with the last run.

## Learned

A prototype should prove the idea, not the design. It showed that searching saved pages by meaning works. The questions it raised (how many results, how much text to send to the LLM) set the next week's work.

## Forum

- [MemoryLane: Overview of the meeting](https://tiet-ucs503.bvraghav.com/d/23-memorylane--overview-of-the-meeting/1) (17 Aug)
- [Working Model Update](https://tiet-ucs503.bvraghav.com/d/45-working-model-update-memorylane/1) (19–20 Aug): Ishan's announcement, the known limits, and the discussion with Sir on storing full text and cutting LLM cost
