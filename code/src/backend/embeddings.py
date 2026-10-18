import logging
from backend.config import EMBEDDING_MODEL, EMBEDDING_DIM, EMBEDDING_QUERY_PREFIX, CHUNK_MAX_WORDS

logger = logging.getLogger(__name__)

BATCH_SIZE = 32
# Rough word-piece tokens per English word.
TOKENS_PER_WORD = 1.4

_model = None

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f'Loading embedding model: {EMBEDDING_MODEL}')
        _model = SentenceTransformer(EMBEDDING_MODEL)
        max_seq_length = getattr(_model, 'max_seq_length', None)
        logger.info(f'Embedding model loaded successfully (max_seq_length={max_seq_length})')
        if max_seq_length and CHUNK_MAX_WORDS * TOKENS_PER_WORD > max_seq_length:
            logger.warning(
                f'CHUNK_MAX_WORDS={CHUNK_MAX_WORDS} (~{int(CHUNK_MAX_WORDS * TOKENS_PER_WORD)} tokens) '
                f'exceeds the model max_seq_length={max_seq_length}; chunk tails will be truncated'
            )
    return _model

def _check_dim(vec: list[float]) -> list[float]:
    if len(vec) != EMBEDDING_DIM:
        raise ValueError(f'Expected {EMBEDDING_DIM}-dimensional embedding, received {len(vec)}')
    return vec

def embed_query(query: str) -> list[float]:
    """Embed a search query, with the model's query prefix (e.g. for BGE)."""
    model = get_model()
    embedding = model.encode(f'{EMBEDDING_QUERY_PREFIX}{query}', normalize_embeddings=True)
    return _check_dim(embedding.tolist())

def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed passages. Callers pass f"{title}\\n\\n{chunk}" for each chunk."""
    if not texts:
        return []
    model = get_model()
    embeddings = model.encode(texts, batch_size=BATCH_SIZE, normalize_embeddings=True)
    return [_check_dim(emb.tolist()) for emb in embeddings]

def is_model_loaded() -> bool:
    return _model is not None
