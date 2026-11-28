# Week 18: Final Report, Repository Documents and Pages on the Device

*23 – 29 Nov 2026*

## What I did

Brought the final report in line with the course's end-semester format, and wrote the repository's own documents.

The report gained:

- a swimlane activity diagram and a level-2 DFD;
- an IEEE 830 requirements specification, user stories and story cards;
- class, sequence, collaboration, state chart and UML component diagrams;
- an IEEE 829 test plan.

The repository gained a README, a manifest, an updated license, this journal, and in the docs a Tutorial, a Usage Guide, a Manifest page and a License page.

I asked the supervisor whether to present the client-server version or a local-first one. The answer was both, with the server as a fallback for large libraries and the limit a user setting. So the extension now keeps pages on the device by default:

- it saves them with the server's own Python code running in the browser (Pyodide);
- it embeds them with the same model (transformers.js, on WebGPU);
- it stores them encrypted in IndexedDB, and searches them with an engine that reproduces Solr's scoring.

Past a size limit, the oldest pages move to the server once the user agrees, and backups are encrypted with a recovery key only the user has. My comparison of the browser-side options (our own BM25 against Orama, and int8 against full-precision vectors) decided the engine's design.

## Problem

The format asked for about ten diagrams and documents the report did not have, but the report had to stay the same length.

For the device engine, "the same results as the server" turned out to be impossible at first. Solr's vector search (HNSW) is approximate: it missed a true neighbour in 71 of 100 SciFact queries, and the browser can't copy its misses. Saving in the browser was also slow, at about 0.8 s a chunk on one CPU thread.

## Fix

The new UML diagrams replaced four older flowcharts and two screenshots that showed the same things. I also let tables float and tightened sections that repeated other chapters. The report stayed at 53 pages.

The server now scores vectors exactly (7 ms against 5 ms). After that, all 117 parity queries give the same pages, order and snippets in both engines, and 119 keyword queries give the same scores. Saving moved to WebGPU, where a 67-chunk page takes 2.6 s. The evaluation was re-run with exact search: MRR@10 0.785, against 0.786 before.

## Learned

Most "missing" documentation already existed in another form. Turning the save and search flowcharts into sequence and collaboration diagrams made them more precise, not just more formal.

"Identical" needs a test, not a reimplementation from memory. Comparing token by token and score by score against a real Solr found the differences, the Thai tokenisation, brackets inside words and HNSW's misses, that reading the code would have missed.
