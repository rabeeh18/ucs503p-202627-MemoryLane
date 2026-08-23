import json
import chromadb
import os
from pathlib import Path
from collections import defaultdict
from typing import List, Dict
import google.generativeai as genai
from dotenv import load_dotenv
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

CHROMA_DB_PATH = "./chroma_db"
OUTPUT_PATH = "./evaluation.json"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env")

genai.configure(api_key=GEMINI_API_KEY)

def get_chromadb_collection():
    """
    Connect to existing ChromaDB and retrieve collection.
    """
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_collection(name="memorylane_chunks")
    return collection

def extract_unique_urls_with_context(collection) -> Dict[str, Dict]:
    """
    Extract unique URLs and representative chunks from ChromaDB.
    
    Returns dict: {
        url: {
            "title": title,
            "chunks": [chunk1, chunk2, ...],
            "chunk_count": N
        }
    }
    """
    all_data = collection.get(include=["documents", "metadatas"])
    
    url_data = defaultdict(lambda: {"title": "", "chunks": [], "chunk_count": 0})
    
    for doc, metadata in zip(all_data["documents"], all_data["metadatas"]):
        url = metadata.get("url")
        title = metadata.get("title", "")
        
        if url not in url_data:
            url_data[url]["title"] = title
        
        url_data[url]["chunks"].append(doc)
        url_data[url]["chunk_count"] += 1
    
    return dict(url_data)

def generate_queries_for_url(url: str, title: str, chunks: List[str]) -> List[str]:
    """
    Use Gemini to generate 3-5 realistic memory queries for a URL.
    
    Queries should simulate how humans remember:
    - "that article about..."
    - "where I read about..."
    - "that page explaining..."
    - Avoid direct titles
    """
    
    representative_chunks = chunks[:3]
    chunk_text = "\n\n---\n\n".join(representative_chunks)
    
    prompt = f"""You are generating realistic human memory queries for information retrieval.

Given this webpage:
- Title: {title}
- URL: {url}
- Content excerpts:

{chunk_text}

Generate 4 realistic memory queries that simulate how a human would remember and search for this information. 

Requirements:
1. Queries should sound natural, as if someone is trying to recall something
2. Do NOT use the exact title
3. Use phrases like "that article about...", "where I read about...", "that page explaining...", "the guide on...", "that tutorial about..."
4. Make queries specific enough to be retrievable but human-like
5. Queries should be diverse - different aspects of the content
6. Each query on a new line

Examples of good queries:
- "that article explaining how attention works in transformers"
- "where I found that tutorial on setting up Kubernetes clusters"
- "the page about managing databases with Docker"
- "that guide on optimizing neural networks"

Generate exactly 4 queries, one per line:"""

    try:
        model = genai.GenerativeModel("gemini-3.5-flash")
        response = model.generate_content(prompt)
        
        queries_text = response.text.strip()
        queries = [q.strip() for q in queries_text.split('\n') if q.strip()]
        
        queries = [q for q in queries if len(q) > 10 and q.lower() not in ['example', 'query']]
        
        return queries[:4]
    
    except Exception as e:
        logger.error(f"Error generating queries for {url}: {e}")
        return []

def generate_evaluation_dataset():
    """
    Main pipeline: extract URLs from ChromaDB and generate evaluation queries.
    """
    logger.info("Connecting to ChromaDB...")
    collection = get_chromadb_collection()
    
    logger.info("Extracting unique URLs and context...")
    url_data = extract_unique_urls_with_context(collection)
    
    logger.info(f"Found {len(url_data)} unique URLs")
    
    evaluation_data = []
    
    for idx, (url, data) in enumerate(url_data.items()):
        title = data["title"]
        chunks = data["chunks"]
        chunk_count = data["chunk_count"]
        
        logger.info(f"[{idx+1}/{len(url_data)}] Generating queries for {url} ({chunk_count} chunks)")
        
        queries = generate_queries_for_url(url, title, chunks)
        
        for query in queries:
            evaluation_data.append({
                "query": query,
                "expected_url": url,
                "title": title,
                "chunk_count": chunk_count
            })
        
        time.sleep(0.5)
    
    logger.info(f"\nGenerated {len(evaluation_data)} evaluation queries")
    
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(evaluation_data, f, indent=2)
    
    logger.info(f"Saved evaluation dataset to {OUTPUT_PATH}")
    
    by_url = defaultdict(list)
    for item in evaluation_data:
        by_url[item["expected_url"]].append(item["query"])
    
    logger.info(f"\nSample queries:")
    for url, queries in list(by_url.items())[:3]:
        logger.info(f"\nURL: {url}")
        for q in queries:
            logger.info(f"  - {q}")

if __name__ == "__main__":
    generate_evaluation_dataset()