# 0008. Keep summaries, on demand and optional

**Status:** Accepted · **Date:** November 2026

## Context

Each search result can be summarised by Google Gemini. It's the only feature that depends on an outside AI service and an API key, and it sends one page's text to Google. Removing it was seriously considered: it adds a cost, a privacy note and a moving part, for something users can do by opening the page.

Summaries were also slow at times. The web app gave up after 15 seconds, while the backend allowed Gemini 20, so a slow summary could finish after the page had already shown an error.

## Decision

Keep summaries, but strictly optional and on demand:

- Nothing is sent to Gemini unless the user presses **Summarise** on one result. Search never waits for it.
- Without a Gemini key, the button explains summaries are unavailable, and everything else works (`/health` reports `gemini: false`).
- Use a light, fast Gemini model (set by `GEMINI_MODEL`); measured at about 3.6 seconds for a long page from the server.

The removal was prepared on a branch (`remove-summaries`) and not merged, so it can be revisited.

## Alternatives

| Option | Why not, for now |
| --- | --- |
| Remove summaries | Simpler and more private, but loses a feature users do use to decide which result to open |
| Summarise every result during search | Makes every search slow, and sends far more text to Google |
| A small model on the server | Too slow on 2 CPUs (20–60 s to read a page) and would slow everyone's searches |
| A second AI service as a fallback | Discussed (Groq), not built yet |

## Consequences

- **Easier:** the feature costs nothing when unused, and the rest of the app doesn't depend on it.
- **Harder:** the [privacy page](../privacy.md) must say what Gemini sees. The Python library used (`google-generativeai`) is no longer updated by Google, so moving to `google-genai` is due.
