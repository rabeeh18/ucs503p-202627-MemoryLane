import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / '.env')

# Solr
SOLR_URL = os.getenv('SOLR_URL', 'http://localhost:8983/solr/memorylane_v2')

# Retrieval
DEFAULT_TOP_K = int(os.getenv('DEFAULT_TOP_K', '5'))
DEFAULT_CANDIDATE_POOL = int(os.getenv('DEFAULT_CANDIDATE_POOL', '50'))
RRF_K = int(os.getenv('RRF_K', '60'))
BM25_WEIGHT = float(os.getenv('BM25_WEIGHT', '1.0'))
VECTOR_WEIGHT = float(os.getenv('VECTOR_WEIGHT', '1.0'))
PAGE_SECOND_CHUNK_WEIGHT = float(os.getenv('PAGE_SECOND_CHUNK_WEIGHT', '0.3'))

# Reranker (cross-encoder, optional)
RERANK_ENABLED = os.getenv('RERANK_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
RERANK_MODEL = os.getenv('RERANK_MODEL', 'cross-encoder/ms-marco-MiniLM-L-6-v2')
RERANK_TOP_N = int(os.getenv('RERANK_TOP_N', '20'))

# Chunking
CHUNK_MAX_WORDS = int(os.getenv('CHUNK_MAX_WORDS', '150'))
CHUNK_MIN_WORDS = int(os.getenv('CHUNK_MIN_WORDS', '40'))
CHUNK_OVERLAP_WORDS = int(os.getenv('CHUNK_OVERLAP_WORDS', '30'))

# Ingestion
MIN_CONTENT_WORDS = 50
# Owner of every page until authentication exists (removed in Phase 4).
LEGACY_USER_ID = os.getenv('LEGACY_USER_ID', 'legacy')

# Embeddings
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'BAAI/bge-small-en-v1.5')
EMBEDDING_DIM = int(os.getenv('EMBEDDING_DIM', '384'))
_BGE_QUERY_PREFIX = 'Represent this sentence for searching relevant passages: '
# An explicitly empty EMBEDDING_QUERY_PREFIX disables the prefix (use that for MiniLM).
EMBEDDING_QUERY_PREFIX = os.getenv(
    'EMBEDDING_QUERY_PREFIX',
    _BGE_QUERY_PREFIX if 'bge' in EMBEDDING_MODEL.lower() else '',
)

# Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.6-flash')

# API
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',')
    if origin.strip()
]
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', '8000'))
