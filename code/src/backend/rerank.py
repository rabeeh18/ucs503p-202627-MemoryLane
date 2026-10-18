import logging
import math
import threading

from backend.config import RERANK_MODEL

logger = logging.getLogger(__name__)

_model = None
_lock = threading.Lock()


def get_reranker():
    """Load the cross-encoder lazily, once per process."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import CrossEncoder
                logger.info(f"Loading reranker model: {RERANK_MODEL}")
                _model = CrossEncoder(RERANK_MODEL)
    return _model


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def rerank_scores(query: str, passages: list[str]) -> list[float]:
    """Cross-encoder relevance of each passage to the query, mapped into (0, 1)
    so page aggregation (best + weighted second-best) stays additive."""
    if not passages:
        return []
    raw = get_reranker().predict([(query, p) for p in passages])
    scores = [float(s) for s in raw]
    if any(s < 0.0 or s > 1.0 for s in scores):
        scores = [_sigmoid(s) for s in scores]
    return scores
