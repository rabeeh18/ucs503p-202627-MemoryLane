# 0010. Remove Export my data

**Status:** Accepted · **Date:** November 2026

## Context

The account menu had **Export my data**, which downloaded every saved page (URL, title, save time and full text) and the user's problem reports as one JSON file (`GET /me/export`).

In practice it wasn't useful. A JSON file of page text can't be opened in anything a user would actually use, nothing could import it again (not even MemoryLane), and the pages themselves are still on the web at their own URLs. It was one more endpoint, menu item and set of tests to maintain.

## Decision

Remove the export: the menu item, the `GET /me/export` endpoint, its helpers and tests, and every mention in the app and the docs. **Delete all my data** stays, so users can still remove everything MemoryLane holds about them.

## Alternatives

| Option | Why not |
| --- | --- |
| Keep the JSON export | Nobody had a use for the file |
| Export in a friendlier format (bookmarks HTML, CSV) | More work for a feature with no demand; can be added if someone asks |

## Consequences

- **Easier:** one less endpoint that reads a user's whole library, so less to secure and test.
- **Harder:** users can't take a copy of their saved text out of MemoryLane. Under data-protection laws such as the GDPR, people can ask for a copy of their data; for a student project this can be handled by hand if anyone ever asks, but a public service would need it back.
- The privacy page now promises only deletion, not export.
