# Week 6: Automatic Capture and the Prototype Report

*31 Aug – 6 Sep 2026*

## What I did

Added automatic capture to the extension, with a page filter, and improved how URLs are stored. My teammate added YouTube transcripts and voice search. I built the evaluation pipeline on a BEIR benchmark, wrote the mid-semester prototype report and updated the documentation.

## Problem

Automatic capture immediately started saving search-engine result pages, which are useless as memories. The same page was also saved several times under slightly different addresses.

## Fix

The page filter (in the extension and the backend) now skips search-result pages, and URLs are normalised before the page id is computed: no `www.`, no fragments or tracking parameters, sorted query parameters.

## Learned

Automatic features need rules for what *not* to do. The evaluation also gave the first real numbers (hybrid Recall@10 0.92), which made later changes measurable.
