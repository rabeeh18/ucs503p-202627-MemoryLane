# Week 15: Real Users, Real Bugs

*2 – 8 Nov 2026*

## What I did

Fixed bugs that real use exposed, hardened the backend, and kept search text out of the access log. Built a test set on a real library and taught search to understand site words, time phrases and URLs ("the reddit post from last week"). Made one Google and one email sign-in with the same verified email share a library.

## Problem

Reddit posts saved one after another collapsed into a single page. Reddit is a single-page app: the address changes, but the page's canonical tag still names the first post.

## Fix

The extension sends the canonical URL only if it matches the current page (same host and path, matching parameters), and the backend ignores a canonical that is a parent of the page.

## Learned

Tests with made-up pages missed this; a real library found it in a day. The personal test set showed the site and time feature raising held-out MRR from 0.79 to 0.94.
