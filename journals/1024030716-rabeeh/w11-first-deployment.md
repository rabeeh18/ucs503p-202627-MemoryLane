# Week 11: Putting It Online

*5 – 11 Oct 2026*

## What I did

Got MemoryLane running on a server for the first time. I committed our Solr configuration and pointed the extension at the server's API. Ishan deployed the web app on Vercel and fixed voice search. I also added a manual trigger to the docs workflow and put the extension zip in the docs.

## Problem

The server needed things that existed only on my machine: our custom Solr configuration, and an API address the extension could reach instead of a local one.

## Fix

Added the Solr configuration (`solrconfig.xml`) to the repository and changed the extension's API endpoint to the server's.

## Learned

"Works on my machine" hides configuration. Anything the app needs (schema, endpoints) has to be in the repository, not set up by hand. A week later this led to setup scripts and Docker Compose.
