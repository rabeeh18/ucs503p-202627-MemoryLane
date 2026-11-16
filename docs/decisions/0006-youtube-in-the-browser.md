# 0006. Fetch YouTube captions in the user's browser

**Status:** Accepted · **Date:** November 2026 · Replaces server-side transcript fetching

## Context

A YouTube page has almost no readable text, so MemoryLane saves a video through its captions. The server fetched them with `youtube-transcript-api`. That worked on a laptop, but on the EC2 server every request failed with `RequestBlocked`: YouTube blocks traffic from cloud providers' IP addresses. Saving a video simply stopped working in production.

The extension already runs in the user's browser, which YouTube doesn't block. But a first attempt to call YouTube's player API from the extension's own background script got `403`, because YouTube rejects requests whose origin is an extension.

## Decision

When the user saves a video, the extension runs a self-contained function **inside the YouTube tab** (`chrome.scripting.executeScript`). From there it calls YouTube's player API, picks a caption track (English first, uploaded before auto-generated) and downloads it. The transcript, title, channel, description and length are then sent to the server with the save (`youtube` in `POST /memory`).

The server uses what the extension sent. It fetches a transcript itself only when an older extension sent nothing, and it builds that URL from a validated video id, never from a URL the browser supplied.

## Alternatives

| Option | Why not |
| --- | --- |
| Route the server's requests through a proxy | Datacenter proxies are blocked too; residential proxies cost money every month and raise terms-of-service concerns |
| The official YouTube Data API | Caption downloads need the video owner's OAuth consent, so it can't fetch other people's captions |
| Save videos from their description only | Most of what someone remembers is what was *said* |

## Consequences

- **Easier:** video saves work on the live site again, and the server makes no YouTube requests in normal use.
- **Harder:** users need extension version 2.2.0 or later. The code depends on YouTube's unofficial player API, which can change without notice; it's isolated in `extension/youtube.js` with its own tests.
- The extension contacts only youtube.com, sends no cookies, and does it only for the video being saved; the [privacy page](../privacy.md#youtube-videos) says so.
