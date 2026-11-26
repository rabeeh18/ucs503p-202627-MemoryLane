# Week 4: Proposal and the First Prototype

*17 – 23 Aug 2026*

## What I did

Wrote and submitted the project proposal (LaTeX). Built the first working prototype: a FastAPI backend that stored page text with embeddings in ChromaDB, and a Chrome extension (with my teammate's backend and extension code) that sent the current page to it. At the end of the week I improved the search and added a seed set of URLs with the first evaluation scripts.

## Problem

Without a repeatable way to judge search, every change was "it feels better". A small first merge conflict also showed that two of us editing the same files needed care.

## Fix

`seed_ingest.py` loads a fixed list of pages, and `generate_eval.py` / `evaluate.py` build queries from them and score the results, so a change could be compared with the last run. The conflict was resolved by hand.

## Learned

A prototype should prove the idea, not the design. It showed that searching saved pages by meaning works, and the seed set started the habit of measuring that carried through to the final evaluation.
