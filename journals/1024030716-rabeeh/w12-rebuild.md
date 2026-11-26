# Week 12: The Rebuild in Seven Phases

*12 – 18 Oct 2026*

## What I did

Rebuilt MemoryLane in seven separately committed phases:

1. retrieval (Reciprocal Rank Fusion, concurrent searches, snippets);
2. bug fixes;
3. a new ingestion pipeline and schema v2 (trafilatura cleaning, 150-word overlapping chunks, BGE embeddings);
4. Cognito sign-in with every Solr query filtered by user;
5. a new web app;
6. a new extension;
7. deployment with Docker Compose and Caddy on EC2.

I then added sentence snippets, the relevance floor and page deletion with undo.

## Problem

The prototype was single-user, ran blocking code inside async handlers, used explicit Solr commits, had hard-coded IP addresses, and mixed min-max scores from BM25 and vectors in a way one outlier could skew.

## Fix

Sync handlers, `commitWithin` writes, rank-based fusion (RRF), configuration from the environment, and a user filter inside the Solr client itself so that isolation cannot be forgotten by an endpoint.

## Learned

Phasing a rewrite into small, tested commits made a huge change reviewable and reversible.
