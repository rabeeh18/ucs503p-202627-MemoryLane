import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / '.env')

# Solr
SOLR_URL = os.getenv('SOLR_URL', 'http://localhost:8983/solr/memorylane')

# Retrieval
DEFAULT_TOP_K = int(os.getenv('DEFAULT_TOP_K', '5'))
DEFAULT_CANDIDATE_POOL = int(os.getenv('DEFAULT_CANDIDATE_POOL', '30'))
BM25_WEIGHT = float(os.getenv('BM25_WEIGHT', '0.5'))
VECTOR_WEIGHT = float(os.getenv('VECTOR_WEIGHT', '0.5'))

# Chunking
TARGET_MIN_WORDS = int(os.getenv('TARGET_MIN_WORDS', '300'))
TARGET_MAX_WORDS = int(os.getenv('TARGET_MAX_WORDS', '500'))

# Embeddings
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
EMBEDDING_DIM = int(os.getenv('EMBEDDING_DIM', '384'))

# Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')

# API
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', '8000'))
