import json
import logging
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import API_PORT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

CORPUS_JSON = ROOT / "evaluation" / "msmarco_data" / "corpus.json"

# 0.0.0.0 is for the server to listen on.
# localhost is used here because this script is a client connecting to it.
BASE_URL = f"http://localhost:{API_PORT}"


def ingest_corpus():
    if not CORPUS_JSON.exists():
        logger.error(f"Corpus file not found: {CORPUS_JSON}")
        sys.exit(1)

    with open(CORPUS_JSON, "r", encoding="utf-8") as f:
        docs = json.load(f)

    logger.info(f"Loaded {len(docs)} documents from corpus.")

    # Check that the MemoryLane API is running.
    try:
        health = httpx.get(
            f"{BASE_URL}/health",
            timeout=30.0
        )
        health.raise_for_status()

        logger.info(
            f"API Health: {health.json()['status']}"
        )

    except Exception as e:
        logger.error(
            f"Failed to connect to MemoryLane API at {BASE_URL}."
        )
        logger.error(f"Error: {e}")
        sys.exit(1)

    success_count = 0
    fail_count = 0

    with httpx.Client(timeout=30.0) as client:

        for i, doc in enumerate(docs, start=1):

            payload = {
                "url": doc["url"],
                "title": doc["title"] or "SciFact Document",
                "content": doc["content"],
                "is_manual": True
            }

            try:
                response = client.post(
                    f"{BASE_URL}/memory",
                    json=payload
                )

                response.raise_for_status()

                success_count += 1

                if i % 50 == 0:
                    logger.info(
                        f"Ingested {i}/{len(docs)} documents..."
                    )

            except Exception as e:
                logger.error(
                    f"Failed to ingest document "
                    f"{i} ({doc['url']}): {e}"
                )

                fail_count += 1

    logger.info(
        f"Ingestion complete. "
        f"Success: {success_count}, "
        f"Failed: {fail_count}"
    )


if __name__ == "__main__":
    ingest_corpus()