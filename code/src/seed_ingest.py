import json
import requests
from datetime import datetime
import chromadb
import os
from pathlib import Path
from urllib.parse import urlparse
import re
from typing import List, Tuple
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import logging
from readability import Document

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

CHROMA_DB_PATH = "./chroma_db"
SEED_URLS_PATH = "./seed_urls.json"
CHUNK_SIZE_WORDS = 400
OVERLAP_WORDS = 50

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def fetch_webpage(url: str) -> Tuple[str, str, str]:
    """
    Fetch and extract webpage content using Readability.
    Returns (content, title, url) or (None, None, url) if failed.
    """
    try:
        response = requests.get(url, timeout=10, headers=headers)
        response.raise_for_status()
        
        doc = Document(response.text)
        content = doc.summary()
        title = doc.title()
        
        if not content or len(content.strip()) < 100:
            logger.warning(f"Skipping {url}: insufficient content")
            return None, None, url
        
        return content, title, url
    except requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None, None, url
    except Exception as e:
        logger.error(f"Error processing {url}: {e}")
        return None, None, url

def is_quality_content(content: str, url: str) -> bool:
    """
    Filter out low-quality content.
    """
    if not content or len(content.strip()) < 200:
        return False
    
    text_lower = content.lower()
    
    skip_patterns = [
        r"404 not found",
        r"page not found",
        r"search results",
        r"no results found",
        r"javascript is required",
        r"you must enable javascript",
    ]
    
    for pattern in skip_patterns:
        if re.search(pattern, text_lower):
            return False
    
    nav_keywords = ["navigation", "cookie", "menu", "sidebar", "footer"]
    nav_count = sum(text_lower.count(kw) for kw in nav_keywords)
    if nav_count > 20:
        return False
    
    html_tags = content.count("<") + content.count(">")
    if html_tags > len(content) * 0.1:
        return False
    
    return True

def clean_text(text: str) -> str:
    """
    Clean extracted HTML/text content.
    """
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text

def chunk_content(text: str, chunk_size: int = CHUNK_SIZE_WORDS, overlap: int = OVERLAP_WORDS) -> List[str]:
    """
    Split text into overlapping chunks by word count.
    """
    text = clean_text(text)
    words = text.split()
    
    if len(words) < chunk_size:
        return [text]
    
    chunks = []
    step = chunk_size - overlap
    
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + chunk_size])
        if len(chunk.strip()) > 50:
            chunks.append(chunk)
    
    return chunks

def initialize_chroma_client():
    """
    Initialize or connect to existing ChromaDB client.
    """
    Path(CHROMA_DB_PATH).mkdir(exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    return client

def get_or_create_collection(client):
    """
    Get existing collection or create new one.
    """
    try:
        collection = client.get_collection(name="memorylane_chunks")
    except:
        collection = client.create_collection(
            name="memorylane_chunks",
            metadata={"hnsw:space": "cosine"}
        )
    return collection

def embed_chunks(chunks: List[str], model) -> List[List[float]]:
    """
    Generate embeddings for chunks.
    """
    embeddings = model.encode(chunks, convert_to_tensor=False).tolist()
    return embeddings

def store_chunks_in_chroma(
    collection,
    chunks: List[str],
    embeddings: List[List[float]],
    url: str,
    title: str
):
    """
    Store chunks in ChromaDB with metadata.
    """
    documents = []
    metadatas = []
    ids = []
    embed_list = []
    
    for chunk_id, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        doc_id = f"{urlparse(url).netloc}_{hash(url) % 10000}_{chunk_id}"
        
        metadata = {
            "url": url,
            "title": title,
            "chunk_id": str(chunk_id),
            "source": "seed",
            "timestamp": datetime.utcnow().isoformat(),
            "domain": urlparse(url).netloc,
        }
        
        documents.append(chunk)
        metadatas.append(metadata)
        ids.append(doc_id)
        embed_list.append(embedding)
    
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embed_list
    )
    
    logger.info(f"Stored {len(chunks)} chunks from {url}")

def process_seed_urls():
    """
    Main pipeline: fetch, extract, chunk, embed, and store all seed URLs.
    """
    with open(SEED_URLS_PATH, 'r') as f:
        urls = json.load(f)
    
    logger.info(f"Loading model all-MiniLM-L6-v2...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    logger.info(f"Initializing ChromaDB...")
    client = initialize_chroma_client()
    collection = get_or_create_collection(client)
    
    processed_count = 0
    skipped_count = 0
    
    for idx, url in enumerate(urls):
        logger.info(f"[{idx+1}/{len(urls)}] Processing {url}")
        
        content, title, _ = fetch_webpage(url)
        
        if not content or not title:
            skipped_count += 1
            continue
        
        if not is_quality_content(content, url):
            logger.info(f"Skipping {url}: quality filter")
            skipped_count += 1
            continue
        
        chunks = chunk_content(content)
        
        if not chunks:
            skipped_count += 1
            continue
        
        embeddings = embed_chunks(chunks, model)
        
        store_chunks_in_chroma(collection, chunks, embeddings, url, title)
        
        processed_count += 1
    
    logger.info(f"\n=== SEED INGESTION COMPLETE ===")
    logger.info(f"Total URLs: {len(urls)}")
    logger.info(f"Successfully processed: {processed_count}")
    logger.info(f"Skipped: {skipped_count}")
    logger.info(f"ChromaDB path: {CHROMA_DB_PATH}")

if __name__ == "__main__":
    process_seed_urls()
