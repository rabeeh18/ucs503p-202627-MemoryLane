import logging
from backend.config import EMBEDDING_MODEL, EMBEDDING_DIM

logger = logging.getLogger(__name__)

_model = None

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f'Loading embedding model: {EMBEDDING_MODEL}')
        _model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info('Embedding model loaded successfully')
    return _model

def get_embedding(text: str) -> list[float]:
    model = get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    vec = embedding.tolist()
    if len(vec) != EMBEDDING_DIM:
        raise ValueError(f'Expected {EMBEDDING_DIM}-dimensional embedding, received {len(vec)}')
    return vec

def get_embeddings(texts: list[str]) -> list[list[float]]:
    model = get_model()
    embeddings = model.encode(texts, normalize_embeddings=True)
    results = []
    for emb in embeddings:
        vec = emb.tolist()
        if len(vec) != EMBEDDING_DIM:
            raise ValueError(f'Expected {EMBEDDING_DIM}-dimensional embedding, received {len(vec)}')
        results.append(vec)
    return results

def is_model_loaded() -> bool:
    return _model is not None
