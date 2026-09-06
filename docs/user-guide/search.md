# Searching Memories

MemoryLane provides a natural-language search interface for previously stored web content.

## Searching

Enter a description of the information you remember and submit the query.

For example:

```text
Find the documentation I read about ROS navigation
```

or:

```text
article explaining ways to reduce database query latency
```

The query does not have to reproduce the exact wording used by the original page.

## What happens after a search

```text
Natural-language query
        ↓
FastAPI search endpoint
        ↓
Candidate retrieval
        ↓
Ranking
        ↓
Webpage-level results
```

The search system can use both exact terminology and semantic similarity to identify useful memories.

## Results

Results are presented as webpages rather than individual internal chunks.

A result contains information such as:

- Rank
- Page title
- URL
- Domain
- Timestamp
- Optional summary

The frontend can also request an on-demand summary for an individual result.

## Search result count

The API accepts a requested result count between 1 and 20. The default is 5.

The internal retrieval process may consider more candidate chunks before producing the final webpage-level list.
