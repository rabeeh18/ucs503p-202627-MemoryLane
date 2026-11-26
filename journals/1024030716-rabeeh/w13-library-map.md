# Week 13: The Library Map

*19 – 25 Oct 2026*

## What I did

Built a "library map": page vectors, related pages, k-means topics with Gemini labels, and an interactive canvas with topic search. Updated the documentation to describe the new system (memorylane.site, Cognito, Caddy, the new retrieval).

## Problem

The first clustering produced only 2 topics for 278 pages, unrelated pages ended up in the same topic, and a floating scroll indicator was invisible.

## Fix

Chose the number of topics by silhouette score with a coherence rule, split oversized topics (9 topics on the same library), and defined the missing `--scroll-pill` colour tokens.

## Learned

A feature can work and still not be worth keeping. The map was slow, depended on Gemini and was rarely used, so in week 17 we removed it (ADR 0009).
