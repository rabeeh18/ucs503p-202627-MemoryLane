# Week 6: Automatic Capture and the Prototype Report

*31 Aug – 6 Sep 2026*

## What I did

Built the features proposed on the forum the week before. I added automatic capture to the extension, with a page filter, and improved how URLs are stored. Ishan added YouTube transcripts and voice search, and shared a demo video of the prototype on 2 Sep. I built the evaluation pipeline on a BEIR benchmark, wrote the mid-semester prototype report and updated the documentation.

## Problem

Automatic capture immediately started saving search-engine result pages, which are useless as memories. The same page was also saved several times under slightly different addresses.

## Fix

The page filter (in the extension and the backend) now skips search-result pages. URLs are normalised before the page id is computed: no `www.`, no fragments or tracking parameters, and query parameters sorted.

## Learned

Automatic features need rules for what *not* to do. Posting the plan first made the week's scope clear, and every proposed feature shipped. The evaluation also gave the first real numbers (hybrid Recall@10 0.92), which made later changes measurable.

## Forum

- [Product Demo Video](https://tiet-ucs503.bvraghav.com/d/69-product-demo-video-memorylane/1) (2 Sep): Ishan's demo of the prototype
- [Proposed next features](https://tiet-ucs503.bvraghav.com/d/58-version-2-update-memorylane/5) (30 Aug), built this week
