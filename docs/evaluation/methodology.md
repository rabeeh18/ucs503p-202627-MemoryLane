# Evaluation Methodology

MemoryLane's retrieval is evaluated on **SciFact**, a scientific-claim retrieval dataset from the BEIR benchmark, adapted to MemoryLane's data model.

## Corpus and queries

- **1,000** SciFact abstracts as documents
- **100** claims as queries
- **106** relevant documents across 115 query–document pairs (binary relevance)

Each document gets a synthetic URL of the form:

```text
https://scifact.org/doc/{document_id}
```

The URLs only give each document a unique identity; titles and text come from SciFact. This is a controlled retrieval benchmark, not a live-web crawl.

## How it runs

The evaluation uses the same code as production:

- Documents are saved through `ingest_page`, the same function behind `POST /memory`, so cleaning, chunking, embedding and indexing are all exercised.
- Queries go through `hybrid_search`, the same function behind `POST /search`.
- Everything runs under the user id `eval`, in a **separate core** (`memorylane_eval` by default), so benchmark data never mixes with real users.

```bash
cd code/src
CORE_NAME=memorylane_eval ./scripts/setup_solr.sh
python -m evaluation.scifact_ingest      # index the 1,000 documents
python -m evaluation.scifact_evaluate    # writes evaluation/scifact_report.json
```

It doesn't need the live server. A throwaway Solr container works just as well, and it keeps the benchmark off the production machine:

```bash
docker run -d --name ml-eval-solr -p 127.0.0.1:8983:8983 solr:9.7
docker exec ml-eval-solr solr create -c memorylane_eval -d _default
CORE_NAME=memorylane_eval ./scripts/setup_solr.sh     # on Windows: scripts/setup_solr.ps1
python -m evaluation.scifact_ingest --solr-base http://localhost:8983/solr
python -m evaluation.scifact_evaluate --solr-base http://localhost:8983/solr
docker rm -f ml-eval-solr                              # when done
```

Indexing takes about two minutes on a laptop, and the evaluation about three.

## Configurations compared

| Configuration | What it uses |
| --- | --- |
| **Hybrid** | The live search: both retrievers, fused |
| **BM25 only** | Keyword retrieval alone |
| **Vector only** | Meaning (embedding) retrieval alone |
| **Hybrid, no relevance floor** | The live search with `MIN_VECTOR_SIMILARITY` at 0, so weak vector-only matches are kept |
| **Hybrid, no second-chunk bonus** | The live search with `PAGE_SECOND_CHUNK_WEIGHT` at 0, so a page is scored by its best chunk alone |

Each configuration is a setting patched for that run only. The single-method runs set the other method's weight to 0 (`BM25_WEIGHT` or `VECTOR_WEIGHT`), which turns that retriever off completely: it isn't queried and none of its results take part. Until November 2026 a zero weight only zeroed its score, so its pages could still fill empty result slots. Numbers measured before then (the earlier table in [Results](results.md)) may be slightly affected.

## Metrics

All use binary relevance (an abstract is either a right answer or not), the top 10 results, and URLs compared after normalisation.

**Quality**

| Metric | In plain words |
| --- | --- |
| **Hit@1, Hit@3, Hit@10** | Share of claims with a right abstract in the first 1, 3 or 10 results |
| **MRR@10** | How high the first right result is, on average (1 = always first, 0.5 = second on average) |
| **Recall@10** | Share of all right abstracts that appear in the top ten |
| **nDCG@10** | How well the right results are ordered, with the top positions counting most |
| **MAP@10** | Average precision at each right result, so it rewards finding *all* of them early |

**Behaviour and speed**

| Metric | In plain words |
| --- | --- |
| **Empty rate** | Share of claims that got no results at all (what the relevance floor could cause) |
| **Average results** | Results returned per claim, at most 10 |
| **Latency p50, p95, mean** | Search time per claim inside the backend process, in ms: the middle case, the slowest 5%, and the average. Network and sign-in checks aren't included. |

**Confidence**

With 100 claims, a few lucky or unlucky ones move the averages. For Hit@1 and MRR@10 the report gives a **95% bootstrap interval**: the claims are resampled with replacement 2,000 times (fixed seed), and the middle 95% of the resulting averages is the range. When two configurations' ranges don't overlap, the difference isn't luck.

Before any timing, every claim is searched once untimed, so the first configuration isn't slowed by cold caches. Each configuration also starts with an empty query-embedding cache. The report (`evaluation/scifact_report.json`) holds the settings used, every configuration's metrics, and the rank of the first right result for every claim.

## Second evaluation: your own library

SciFact measures scientific claims, not how people look for pages they've read. The second evaluation runs on a real library, with queries written by its owner: for each page, how they would actually search for it.

Each query has a **category**, so a change shows up where it should:

| Category | The query... | Example |
| --- | --- | --- |
| `navigational` | names the page, by its title or what it's called | "nav2 behavior trees docs" |
| `site` | names the site it was on | "reddit post about rust lifetimes" |
| `topic` | says only what it was about | "baking bread with a starter" |
| `time` | says when it was seen | "the article on caching from last week" |

`evaluation/evaluate.py` reports Recall@1/3/5/10 and MRR overall and per category, the rank of the expected page for every query, and the queries where it wasn't first. Queries whose expected URL isn't one of the user's saved pages are listed and left out of the metrics. That usually means a URL copied from the browser rather than the one MemoryLane stored, and no ranking change could ever find it.

On the server, with the eval file going in on stdin and the report coming out on stdout (nothing is written inside the container):

```bash
cd code/src
# 1. Your user id (page counts per user)
docker compose exec -T backend python -m evaluation.generate_eval --core memorylane_v2 --list-users

# 2. A starting set: a random sample of your pages, queries left empty
docker compose exec -T backend python -m evaluation.generate_eval --core memorylane_v2 \
    --user-id <user id> --starter --limit 50 --out - > evaluation/personal.json

# 3. Fill in each query and category, delete pages you don't remember, then:
docker compose exec -T backend python -m evaluation.evaluate --core memorylane_v2 \
    --user-id <user id> --eval-file - --out - \
    < evaluation/personal.json > evaluation/personal_baseline.json

# 4. After a search change, run step 3 again into personal_report.json and compare
python3 evaluation/compare.py evaluation/personal_baseline.json evaluation/personal_report.json
```

`compare.py` needs only the standard library, so it runs on the host. It prints each metric with its change, and every query whose rank went up or down.

A feature behind a setting can be compared without deploying old code, since `docker compose exec -e` overrides it for that one run. For example, search with and without [site, time and URL handling](../architecture/retrieval.md#site-time-and-url-in-the-query):

```bash
docker compose exec -T -e QUERY_INTENT_ENABLED=false backend python -m evaluation.evaluate \
    --core memorylane_v2 --user-id <user id> --eval-file - --out - \
    < evaluation/personal.json > evaluation/personal_off.json
docker compose exec -T backend python -m evaluation.evaluate \
    --core memorylane_v2 --user-id <user id> --eval-file - --out - \
    < evaluation/personal.json > evaluation/personal_on.json
python3 evaluation/compare.py evaluation/personal_off.json evaluation/personal_on.json
```

### Results on a development library

Tested on a copy of an early real library: 31 browsed pages from about a dozen sites, among about 1,000 SciFact pages as distractors, with queries written by hand.

| Set | Search | Right page first | MRR |
| --- | --- | --- | --- |
| 35 queries, used while building it | before | 0.86 | 0.900 |
| | after | 0.94 | 0.971 |
| 18 held-out queries | before | 0.72 | 0.787 |
| | after | 0.94 | 0.944 |

The held-out set was written after the feature and not tuned on, except for one fix it led to (browsing verbs like *look* added to the filler words), after which it scores 1.00. Most of the gain is in site queries (held-out MRR 0.75 → 1.00) and time queries (0.38 → 1.00, three queries); topic-only queries don't change, and neither do SciFact's 100 test claims (MRR@10 0.581 either way). Both sets are small, so the numbers on your own library are what count.

`evaluation/personal*` is git-ignored and kept out of the Docker image, since these files hold real URLs and titles.

Queries made from page titles (`generate_eval.py` without `--starter`) are near-certain hits for keyword search, so they say little about precision. The starter set is meant to be written by hand.
