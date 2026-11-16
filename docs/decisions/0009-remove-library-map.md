# 0009. Remove the library map

**Status:** Accepted · **Date:** November 2026

## Context

In October 2026 MemoryLane gained a **library map**: saved pages clustered into named topics (k-means over page vectors, names from keywords and Gemini), drawn as a zoomable map with related pages and "search within a topic".

It was the most complex part of the app: clustering, topic naming in the background, a layout algorithm, a per-user cache, stale-topic handling (`409` responses), and a large SVG canvas in the web app. It also had a steady stream of bugs. Meanwhile it wasn't how people found pages: they searched. With little time left in the project, the map was costing more than it gave.

## Decision

Remove the map entirely: the Map page, `GET /map` and `/map/search`, topic search, Gemini topic naming, the map cache, their settings, tests and docs, and the direct `scikit-learn` dependency.

Keep the **page vectors** and `GET /memory/{page_id}/related`. They're small, tested and isolated, and a future feature (for example "related pages" on a result) can use them.

## Alternatives

| Option | Why not |
| --- | --- |
| Keep fixing the map | Ongoing effort on a feature that wasn't central to finding pages |
| Hide it behind a setting | The code, its tests and its Gemini calls would still need maintaining |
| Replace it with a simpler topic list | Still needs the clustering and naming, which was where most of the bugs were |

## Consequences

- **Easier:** about 4,300 fewer lines of code, tests and docs to maintain, fewer Gemini calls, no map cache, and a simpler header.
- **Harder:** no visual overview of a library, and related pages have no place in the web app for now.
- The code is in git history (commit `499194d` removed it), so it can be restored if the idea returns.
