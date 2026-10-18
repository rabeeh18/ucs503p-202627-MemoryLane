import logging
import re
import httpx
from backend.config import SOLR_URL

logger = logging.getLogger(__name__)

# Dense vectors must stay lists. Everything else Solr may return as a
# one-element array (especially text_general fields) should be a scalar.
_VECTOR_FIELDS = {"embedding"}

# Stored fields returned for chunk documents. `embedding` is not stored.
CHUNK_FIELDS = (
    "id,user_id,page_id,url,title,domain,text,chunk_id,total_chunks,"
    "timestamp,content_hash,embedding_model"
)


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


MAX_QUERY_CHARS = 500
COMMIT_WITHIN_MS = 1000
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def sanitize_query(query: str) -> str:
    """Replace control characters with spaces and cap the query length."""
    cleaned = _CONTROL_CHARS.sub(" ", query or "").strip()
    return cleaned[:MAX_QUERY_CHARS]


def _escape_phrase(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def term_query(field: str, value: str) -> str:
    """Exact-match query on one field; no query-syntax escaping needed."""
    return "{!term f=" + field + "}" + value


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

    def _select(self, params: dict) -> dict:
        response = self.client.get(f"{self.base_url}/select", params={**params, "wt": "json"})
        response.raise_for_status()
        return response.json()

    def _update(self, body) -> None:
        response = self.client.post(
            f"{self.base_url}/update?commitWithin={COMMIT_WITHIN_MS}",
            json=body,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

    def upsert_page_chunks(self, page_id: str, docs: list[dict]) -> None:
        """Replace a page's chunks without a window where the page has none.

        Chunk ids are deterministic, so adding overwrites existing chunks in place.
        Any stale chunks beyond the new count are then deleted. Both requests use
        commitWithin instead of an explicit commit.
        """
        self._update(docs)
        stale = f'page_id:"{_escape_phrase(page_id)}" AND chunk_id:[{len(docs)} TO *]'
        self._update({"delete": {"query": stale}})

    def delete_user(self, user_id: str) -> None:
        """Delete every chunk owned by user_id."""
        self._update({"delete": {"query": term_query("user_id", user_id)}})

    def bm25_search(self, query: str, rows: int = 30) -> list[dict]:
        """Standard BM25 search on text and title fields.
        Returns list of chunk docs (CHUNK_FIELDS) with score.
        """
        data = self._select({
            "q": sanitize_query(query),
            "defType": "edismax",
            "qf": "title^2 text",
            "pf": "text^2 title^3",
            "uf": "-*",
            "fl": CHUNK_FIELDS + ",score",
            "rows": rows,
        })
        docs = data.get("response", {}).get("docs", [])
        return [normalize_solr_doc(doc) for doc in docs]

    def knn_search(self, vector: list[float], k: int = 30) -> list[dict]:
        """Dense vector KNN search.
        Returns list of chunk docs (CHUNK_FIELDS) with score.
        """
        url = f"{self.base_url}/select"
        vector_str = "[" + ",".join(str(v) for v in vector) + "]"
        payload = {
            "query": f"{{!knn f=embedding topK={k}}}{vector_str}",
            "fields": CHUNK_FIELDS + ",score",
            "limit": k
        }
        response = self.client.post(url, json=payload, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        data = response.json()
        docs = data.get("response", {}).get("docs", [])
        return [normalize_solr_doc(doc) for doc in docs]

    def get_page_head(self, page_id: str) -> dict | None:
        """First chunk (chunk_id 0) of a page, which carries the page's metadata."""
        data = self._select({
            "q": term_query("page_id", page_id),
            "fq": "chunk_id:0",
            "fl": CHUNK_FIELDS,
            "rows": 1,
        })
        docs = data.get("response", {}).get("docs", [])
        return normalize_solr_doc(docs[0]) if docs else None

    def get_chunks_by_page_id(self, page_id: str) -> list[dict]:
        """Fetch all chunks for a given page_id, in order."""
        data = self._select({
            "q": term_query("page_id", page_id),
            "fl": CHUNK_FIELDS,
            "rows": 1000,
            "sort": "chunk_id asc",
        })
        return [normalize_solr_doc(doc) for doc in data.get("response", {}).get("docs", [])]

    def scan(self, fields: str, query: str = "*:*", rows: int = 500):
        """Yield every matching document, paging with cursorMark (sorted by id)."""
        cursor = "*"
        while True:
            data = self._select({
                "q": query,
                "fl": fields,
                "rows": rows,
                "sort": "id asc",
                "cursorMark": cursor,
            })
            for doc in data.get("response", {}).get("docs", []):
                yield normalize_solr_doc(doc)
            next_cursor = data.get("nextCursorMark")
            if not next_cursor or next_cursor == cursor:
                return
            cursor = next_cursor

    def get_document_count(self) -> int:
        """Get total document count."""
        data = self._select({"q": "*:*", "rows": 0})
        return data.get("response", {}).get("numFound", 0)


# Module-level singleton
_client = None

def get_solr_client() -> SolrClient:
    global _client
    if _client is None:
        _client = SolrClient()
    return _client
