# Week 14: Making Search Faster

*26 Oct – 1 Nov 2026*

## What I did

Profiled a search stage by stage and sped up snippet generation.

## Problem

Snippets embedded candidate sentences for every result on every search. On the server's CPU this was the slowest stage, slower than the searches themselves.

## Fix

Sentences are now chosen by the query words they contain. The embedding model is used only when no sentence shares a word with the query (a pure search by meaning), and then only for the first few readable sentences.

## Learned

Measure before optimising. The per-stage timings added in week 12 pointed straight at the problem, which was not where I expected.
