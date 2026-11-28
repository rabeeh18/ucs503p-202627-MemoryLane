# Design Decisions

Each page here is an **architecture decision record** (ADR): one important choice, why it was made, what else was considered, and what it costs. They follow Michael Nygard's format (Context, Decision, Consequences), with the alternatives spelled out.

A decision that changes later isn't edited away. A new record replaces it, and the old one is marked *Superseded*, so the history stays readable.

| # | Decision | Status | Date |
| --- | --- | --- | --- |
| [0001](0001-solr.md) | One Solr core for keyword and vector search | Accepted | Aug 2026 |
| [0002](0002-reciprocal-rank-fusion.md) | Fuse rankings with Reciprocal Rank Fusion | Accepted | Oct 2026 |
| [0003](0003-relevance-floor.md) | Drop weak matches with a relevance floor | Accepted | Oct 2026, revised Nov 2026 |
| [0004](0004-one-ec2-instance.md) | Run everything on one EC2 instance | Accepted | Oct 2026 |
| [0005](0005-link-sign-ins-by-email.md) | Link Google and email sign-ins by verified email | Accepted | Nov 2026 |
| [0006](0006-youtube-in-the-browser.md) | Fetch YouTube captions in the user's browser | Accepted | Nov 2026 |
| [0007](0007-store-reports-before-emailing.md) | Store problem reports before emailing them | Accepted | Nov 2026 |
| [0008](0008-keep-summaries-optional.md) | Keep summaries, on demand and optional | Accepted | Nov 2026 |
| [0009](0009-remove-library-map.md) | Remove the library map | Accepted | Nov 2026 |
| [0010](0010-remove-export.md) | Remove Export my data | Accepted | Nov 2026 |
| [0011](0011-auto-capture-keeps-only-content.md) | Automatic capture keeps only pages that read like content | Accepted | Nov 2026 |
| [0012](0012-local-first-storage.md) | Keep pages on the device by default, with the server as a fallback | Accepted | Nov 2026 |
| [0013](0013-exact-vector-search.md) | Score vectors exactly instead of with HNSW | Accepted | Nov 2026 |
| [0014](0014-own-bm25-no-orama.md) | Own BM25 and a plain vector scan in the browser, not Orama | Accepted | Nov 2026 |
| [0015](0015-server-code-in-the-browser.md) | Run the server's saving code in the browser with Pyodide | Accepted | Nov 2026 |
| [0016](0016-encrypt-local-pages-and-backups.md) | Encrypt pages on the device, and back them up with a key only the user has | Accepted | Nov 2026 |

## Template

```text
# NNNN. Title

Status: Proposed | Accepted | Superseded by NNNN
Date:

## Context        What problem, and what forces are at play
## Decision       What we chose
## Alternatives   What else was considered, and why not
## Consequences   What gets easier, what gets harder
```
