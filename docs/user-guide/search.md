# Searching

Describe what you remember in the search box on the home page. Press `/` anywhere on the home page to jump to it.

```text
the article on reducing database query latency
```

```text
docs about ROS navigation
```

The query doesn't need the page's exact words. MemoryLane matches by meaning as well as by keywords.

## Saying where or when

If you remember the site or when you saw it, say so. MemoryLane ranks the pages that fit higher:

| You type | MemoryLane looks first at |
| --- | --- |
| `reddit post about rust lifetimes` | your reddit.com pages about rust lifetimes |
| `rotten tomatoes reviews of dune` | your Rotten Tomatoes pages about Dune |
| `nvidia docs on cuda graphs` | your pages from nvidia.com and docs.nvidia.com |
| `what i read yesterday` | pages you saved yesterday, nearest first |
| `the article from last week about caching` | pages saved in the last two weeks about caching |
| `recipe videos from 1 september` | pages saved around 1 September |
| `github.com/tokio-rs/axum` | that saved page, then the site's others |

A site counts when it's one you've saved pages from, by its name without `www.` or the ending (`wikipedia`, `github`, `nvidia`; `wiki` and `yt` work too). Times can be today, yesterday, *N* days/weeks/months ago, this or last week/month/year, recently, a date (`31 august`, `aug 31`), a month after *in*/*from* (`in march`), or a year after *from* or with a word like *saved* (`what I saved in 2025`).

These are hints, not filters: a page from another site or time still shows up if it matches better.

## Results

Each result shows:

- The page title, linking to the page
- The site, with a letter tile for the domain
- A **snippet**: two or three sentences from the page that best match your query, with the query words highlighted
- When you saved it
- **Summarise**, for a short summary of that page

Up to 10 pages are shown. Pages that only loosely match your query are left out instead of padding the list, so a short list means nothing else was close enough. If nothing matches, MemoryLane suggests describing the idea rather than exact words.

## Keyboard

| Key | Action |
| --- | --- |
| `↑` `↓` | Move between results |
| `Enter` | Open the selected page |
| `Shift` + `Del` | Delete the selected page (with undo) |
| `Esc` | Clear the search |

## Searching within a topic

From the [library map](map.md), **Search only these pages** limits a search to one topic. The results page shows the topic as a chip; remove it to search everything again. If the topic changed because you saved or deleted pages in the meantime, MemoryLane finds the same topic by name, or searches all pages and tells you.

## How it works

Every search runs a keyword search (BM25) and a meaning search (vector KNN) over your pages at the same time, then combines them. See [Retrieval Architecture](../architecture/retrieval.md).
