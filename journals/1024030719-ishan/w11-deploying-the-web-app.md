# Week 11: Deploying the Web App

*5 – 11 Oct 2026*

## What I did

While Rabeeh put the backend on a server, I deployed the web app on Vercel and connected it to that backend. Before that, I brought the interface up to date: results in both the web app and the extension popup can now be sorted by relevance or by when the page was visited. I also reworked voice search so it fails clearly instead of silently.

## Problem

Two things broke once the app was online. Vercel's rewrite sent every `/api/...` request to the backend's root address, dropping the rest of the path, so searches failed. And voice search gave no useful feedback: an unsupported browser showed a pop-up alert, while a blocked microphone or a missing speech service did nothing at all.

## Fix

The rewrite now forwards the full path (`/api/:path*` to the same path on the backend). Voice search sets the language to English (India), shows a specific message for each failure (microphone blocked, no microphone, no speech heard, speech service unreachable, unsupported browser), ignores a stop the user asked for, and releases the microphone when the page closes.

## Learned

A deployment is not done until every route has been tried through it. Clear error messages matter most for features that depend on the browser, because the user cannot see why they failed. A week later the team moved the web app to the same server as the backend, behind Caddy, which removed this proxy step altogether.
