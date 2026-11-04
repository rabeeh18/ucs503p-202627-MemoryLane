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

## Configurations compared

| Configuration | What it uses |
| --- | --- |
| **BM25 only** | Lexical retrieval |
| **Vector only** | Dense retrieval |
| **Hybrid** | The production pipeline: both, fused |

## Metrics

- **MRR@10**: how early the first relevant result appears
- **Recall@10**: how much of the relevant set is in the top ten
- **nDCG@10**: how well the relevant results are ordered

Relevant URLs are compared after normalisation.

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

`evaluation/personal*` is git-ignored and kept out of the Docker image, since these files hold real URLs and titles.

Queries made from page titles (`generate_eval.py` without `--starter`) are near-certain hits for keyword search, so they say little about precision. The starter set is meant to be written by hand.
