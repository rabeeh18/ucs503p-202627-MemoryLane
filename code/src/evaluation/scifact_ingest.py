"""Ingest the SciFact corpus in-process into the evaluation core.

Usage (from project root):
    python -m evaluation.scifact_ingest [--core memorylane_eval]
"""
import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.ingest import IngestError, ingest_page
from evaluation.common import add_core_args, eval_solr

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

CORPUS_JSON = ROOT / "evaluation" / "scifact_data" / "corpus.json"


def ingest_corpus(args):
    if not CORPUS_JSON.exists():
        logger.error(f"Corpus file not found: {CORPUS_JSON}")
        sys.exit(1)

    with open(CORPUS_JSON, "r", encoding="utf-8") as f:
        docs = json.load(f)

    logger.info(f"Loaded {len(docs)} documents from corpus.")
    solr = eval_solr(args)

    success_count = 0
    fail_count = 0

    for i, doc in enumerate(docs, start=1):
        try:
            ingest_page(
                args.user_id,
                doc["url"],
                doc["title"] or "SciFact Document",
                doc["content"],
                is_manual=True,
                solr=solr,
            )
            success_count += 1
            if i % 50 == 0:
                logger.info(f"Ingested {i}/{len(docs)} documents...")
        except (IngestError, Exception) as e:
            logger.error(f"Failed to ingest document {i} ({doc['url']}): {e}")
            fail_count += 1

    logger.info(
        f"Ingestion complete. "
        f"Success: {success_count}, "
        f"Failed: {fail_count}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest SciFact into the evaluation core")
    add_core_args(parser)
    ingest_corpus(parser.parse_args())
