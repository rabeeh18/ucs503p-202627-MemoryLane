import logging
import httpx
from backend.config import SOLR_URL

logger = logging.getLogger(__name__)

# Dense vectors must stay lists. Everything else Solr may return as a
# one-element array (especially text_general fields) should be a scalar.
_VECTOR_FIELDS = {"embedding"}


def unwrap_solr_value(value, field_name: str = ""):
    """Turn Solr single-element lists into scalars; leave real multi-values and vectors."""
    if field_name in _VECTOR_FIELDS:
        return value
    if isinstance(value, (list, tuple)) and len(value) == 1:
        return unwrap_solr_value(value[0], field_name)
    return value


def normalize_solr_doc(doc: dict) -> dict:
    """Normalize a Solr document so stored fields are scalars where appropriate."""
    if not doc:
        return doc
    return {key: unwrap_solr_value(value, key) for key, value in doc.items()}


class SolrClient:
    def __init__(self, base_url: str = None):
        self.base_url = base_url or SOLR_URL
        self.client = httpx.Client(timeout=30.0)
    
    def ping(self) -> bool:
        """Check if Solr is reachable."""
        try:
            response = self.client.get(f"{self.base_url}/admin/ping")
            return response.status_code == 200
        except Exception:
            return False
    
    def add_documents(self, docs: list[dict]) -> dict:
        """Index documents into Solr."""
        url = f"{self.base_url}/update?commit=true"
        response = self.client.post(url, json=docs, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        return response.json()
    
    def delete_by_query(self, query: str) -> dict:
        """Delete documents matching query."""
        url = f"{self.base_url}/update?commit=true"
        response = self.client.post(url, json={"delete": {"query": query}}, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        return response.json()
    
    def commit(self) -> dict:
        """Explicit commit."""
        url = f"{self.base_url}/update?commit=true"
        response = self.client.post(url, json={}, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        return response.json()
    
    def bm25_search(self, query: str, rows: int = 30) -> list[dict]:
        """Standard BM25 search on text and title fields.
        Returns list of {id, webpage_id, url, title, domain, text, chunk_id, total_chunks, timestamp, score}.
        """
        url = f"{self.base_url}/select"
        params = {
            "q": query,
            "defType": "edismax",
            "qf": "text title^2",
            "fl": "id,webpage_id,url,title,domain,text,chunk_id,total_chunks,timestamp,score",
            "rows": rows,
            "wt": "json"
        }
        response = self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        docs = data.get("response", {}).get("docs", [])
        return [normalize_solr_doc(doc) for doc in docs]
    
    def knn_search(self, vector: list[float], k: int = 30) -> list[dict]:
        """Dense vector KNN search.
        Returns list of {id, webpage_id, url, title, domain, chunk_id, total_chunks, timestamp, score}.
        """
        url = f"{self.base_url}/select"
        vector_str = "[" + ",".join(str(v) for v in vector) + "]"
        payload = {
            "query": f"{{!knn f=embedding topK={k}}}{vector_str}",
            "fields": "id,webpage_id,url,title,domain,text,chunk_id,total_chunks,timestamp,score",
            "limit": k
        }
        response = self.client.post(url, json=payload, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        data = response.json()
        docs = data.get("response", {}).get("docs", [])
        return [normalize_solr_doc(doc) for doc in docs]
    
    def get_by_url(self, url: str) -> list[dict]:
        """Fetch chunks whose stored url matches exactly (normalized URL)."""
        url_select = f"{self.base_url}/select"
        params = {
            "q": "{!term f=url}" + url,
            "fl": "id,webpage_id,url,title,domain,text,chunk_id,total_chunks,timestamp",
            "rows": 1,
            "wt": "json",
        }
        response = self.client.get(url_select, params=params)
        response.raise_for_status()
        data = response.json()
        return [normalize_solr_doc(doc) for doc in data.get("response", {}).get("docs", [])]

    def get_by_webpage_id(self, webpage_id: str) -> list[dict]:
        """Fetch all chunks for a given webpage_id."""
        url = f"{self.base_url}/select"
        params = {
            "q": f'webpage_id:"{webpage_id}"',
            "fl": "id,webpage_id,url,title,domain,text,chunk_id,total_chunks,timestamp",
            "rows": 1000,
            "sort": "chunk_id asc",
            "wt": "json"
        }
        response = self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return [normalize_solr_doc(doc) for doc in data.get("response", {}).get("docs", [])]

    def get_chunks_by_webpage_id(self, webpage_id: str) -> list[dict]:
        """Alias for get_by_webpage_id."""
        return self.get_by_webpage_id(webpage_id)
    
    def get_document_count(self) -> int:
        """Get total document count."""
        url = f"{self.base_url}/select"
        params = {"q": "*:*", "rows": 0, "wt": "json"}
        response = self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("response", {}).get("numFound", 0)


# Module-level singleton
_client = None

def get_solr_client() -> SolrClient:
    global _client
    if _client is None:
        _client = SolrClient()
    return _client
