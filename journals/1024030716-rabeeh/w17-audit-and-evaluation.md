# Week 17: The Audit, and a Ranking Bug the Numbers Found

*16 – 22 Nov 2026*

## What I did

Removed the library map and "Export my data", added design decision records, a glossary and diagrams to the docs, and fixed every bug from a structured audit. Rebuilt automatic capture, added meaning-based search to the docs site, re-ran the SciFact evaluation with seven metrics, and wrote the final report.

## Problems

- An outdated extension auto-saved a Gmail inbox.
- The HTTP client logged Solr URLs, which contained search text.
- Rapid reloads signed users out.
- Deleted pages came back after a refresh.
- Gemini summaries split words in two.
- Most important: the re-evaluation showed search had got *worse* than the prototype (MRR@10 0.60 against 0.75).

## Fixes

- Capture now keeps only pages that were read and look like content, and the server re-checks every automatic save.
- Those loggers were quietened.
- Only a refused refresh token ends a session.
- Deletes are visible to the next read.
- The parts of Gemini's response are joined without line breaks.
- The ranking cause was a bonus for a page's second matching chunk, which with RRF outweighed the gaps between ranks and favoured long pages. Setting it to zero gave Hit@1 0.71 and MRR@10 0.79.

## Learned

Without measuring, I would never have found the biggest improvement of the semester.
