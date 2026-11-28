# Week 6: YouTube, Voice Search and the Demo Video

*31 Aug – 6 Sep 2026*

## What I did

Recorded a video demonstration of the prototype and shared it on the forum on 2 Sep, to show how we expect people to use MemoryLane. Then I added two features. YouTube videos are now saved through their transcripts, and the web app has voice search: a microphone button in the search bar that fills in the query as you speak. I also removed the old hybrid search module, since search now ran in Solr.

## Problem

A YouTube page holds almost no useful text: the video's content is in what is said, not on the page. Saving the page as it was gave search nothing to match. YouTube Shorts were a second problem, short clips that would clutter the library.

## Fix

When a saved address is a YouTube video, the backend recognises it (including `youtu.be`, `/embed/` and mobile links), extracts the video id and fetches its transcript, which replaces the page text before it is chunked and embedded. If no transcript is available, the page text is kept. Shorts are skipped on purpose.

## Learned

The best text to search is not always the text on the page. Voice search used the browser's own speech recognition, so it needed no server, but it only works in some browsers, a limit that came back to us in week 11.

## Forum

- [Product Demo Video](https://tiet-ucs503.bvraghav.com/d/69-product-demo-video-memorylane/1) (2 Sep): my video demonstration of the prototype ([watch on YouTube](https://youtu.be/a2k7N6c0MOU))
