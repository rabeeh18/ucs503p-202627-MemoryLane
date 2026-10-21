# Library Map

The library map (`GET /map`) turns a user's saved pages into named topics laid out on a 2-D canvas. It is built on request from the page vectors already in Solr, in `backend/library_map.py`, and cached per user.

## Page vectors

When a page is saved, its **page vector** (the normalised mean of its chunk vectors) is stored in `page_embedding` on chunk 0. The map and related pages both use it.

**Related pages** (`GET /memory/{id}/related`) is a KNN over page vectors, pre-filtered to the user's pages minus the page itself.

## Building the map

```text
Newest MAP_MAX_PAGES (2,000) page vectors (cursor scan)
        ↓
PCA to ~50 dimensions, normalise
        ↓
k-means for each k in a range; keep the best silhouette
        ↓
Split any topic holding > 25% of pages (and > 30 pages)
        ↓
Unclustered: pages far from their centre, and loose "topics"
        ↓
Topic names
        ↓
Layout: ovals packed in rows, then relaxed
        ↓
Links: page → 2 nearest in topic; topic ↔ similar topic
```

### Choosing the number of topics

For \(n\) pages, k-means is tried for every \(k\) from \(\mathrm{clamp}(\mathrm{round}(\sqrt{n}/2), 3, 10)\) to \(\min(14, n/8)\). The \(k\) with the best silhouette score (cosine, on a sample, fixed seed) wins. Topics holding more than a quarter of the library are split in two, repeatedly, so one broad topic can't swallow the map. On 278 SciFact abstracts this gives 9 topics.

### Outliers

A page whose cosine similarity to its topic centre is below `MAP_OUTLIER_SIMILARITY` (0.35) is left unclustered. So is a whole "topic" whose pages don't hang together (mean pairwise similarity below 0.35²). Unclustered pages are drawn between the topics they are closest to.

## Topic names

1. **Gemini**, in one call for the whole map: for each topic it sees up to 10 page titles, a keyword hint, and the names already taken. It is asked for distinct, specific names of 1–3 words. Generic names ("Articles", "Resources", ...) and duplicates are rejected.
2. **Fallback**: c-TF-IDF over the unigrams and bigrams of each topic's titles and descriptions, with generic words and title filler removed, made into distinct Title Case names.

Every fallback is logged at WARNING. Names are cached by topic membership, so an unchanged topic keeps its name and costs no Gemini call.

## Layout

All coordinates are in a 0–1 box, drawn into a 1400 × 900 world:

- Each topic is an ellipse whose **area is proportional to its page count**. Together the ellipses cover about 30% of the canvas.
- Topics are **packed into centred rows** matching the canvas's aspect ratio, ordered by a PCA of their centres so similar topics sit near each other. A few rounds of repulsion and centre pull then even out the gaps.
- Each topic's **label space is reserved**, so a label never sits on another oval.
- Pages are placed inside their ellipse by a local PCA, so similar pages sit together.

## Links

- **Inside a topic**: each page links to its 2 nearest neighbours. These are drawn only for the hovered or selected topic, and for the selected page.
- **Between topics**: topics whose centres have cosine similarity above `MAP_CROSS_TOPIC_SIMILARITY` (0.65) get a dashed oval-to-oval link, at most 2 per topic, strongest first.

## Caching and freshness

`MapService` keeps an LRU of up to 50 users' maps for 10 minutes. Saving or deleting a page invalidates that user's map, and each map has a `version`. `GET /map/search` and topic-filtered search use the cached map; if the version a client holds is gone, topic search returns `409`.

## Performance

Building a 2,000-page map takes about 0.2 s on a laptop, most of it k-means. The web app keeps the canvas readable and cheap to draw by dimming dots in libraries over 150 pages until you zoom past 1.6×, and by drawing only the links that matter for the current hover or selection.
