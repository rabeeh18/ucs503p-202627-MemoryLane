import logging
import re
import httpx
from backend.config import SOLR_URL

logger = logging.getLogger(__name__)

# Dense vectors must stay lists. Everything else Solr may return as a
# one-element array (especially text_general fields) should be a scalar.
_VECTOR_FIELDS = {"embedding", "page_embedding"}

# Stored fields returned for chunk documents. `embedding` is not stored.
CHUNK_FIELDS = (
    "id,user_id,page_id,url,title,domain,text,chunk_id,total_chunks,"
    "timestamp,content_hash,embedding_model,description"
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


_QUERY_SYNTAX = re.compile(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)')
_OPERATORS = re.compile(r"\b(AND|OR|NOT|TO)\b")


def escape_query(query: str) -> str:
    """The query as plain words: query syntax escaped, operators lowercased."""
    return _OPERATORS.sub(lambda m: m.group(1).lower(), _QUERY_SYNTAX.sub(r"\\\1", query or ""))


_SOLR_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_USER_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def is_valid_user_id(user_id: str) -> bool:
    return isinstance(user_id, str) and bool(_USER_ID_RE.match(user_id))


def _require_user(user_id: str) -> str:
    """Every scoped call must carry a well-formed user id."""
    if not is_valid_user_id(user_id):
        raise ValueError("A valid user_id is required for this Solr operation")
    return user_id


def _escape_phrase(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def term_query(field: str, value: str) -> str:
    """Exact-match query on one field; no query-syntax escaping needed."""
    return "{!term f=" + field + "}" + value


def page_ids_filter(page_ids) -> str:
    """Filter to a set of page ids (e.g. the pages of one map topic)."""
    ids = [p for p in page_ids if p]
    if not ids:
        return "-*:*"  # matches nothing
    if any("," in p for p in ids):
        raise ValueError("page ids must not contain commas")
    return "{!terms f=page_id}" + ",".join(ids)


def domains_filter(domains) -> str:
    """Filter to pages from any of `domains` (exact, as stored)."""
    names = sorted({d for d in domains if d and "," not in d})
    return "{!terms f=domain}" + ",".join(names) if names else "-*:*"


def saved_between_filter(start: str, end: str) -> str:
    """Filter to pages saved from `start` (inclusive) to `end` (exclusive), Solr dates."""
    return f"timestamp:[{start} TO {end}}}"


def user_filter(user_id: str) -> str:
    """The filter every scoped read, write and delete carries."""
    return term_query("user_id", _require_user(user_id))


class SolrClient:
    """Solr access. Every method that touches chunks takes `user_id` and adds the
    `{!term f=user_id}<user_id>` filter; `scan_unscoped` exists only for re-indexing
    an old core that predates user ids."""

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

    def _select(self, params: dict, post: bool = False) -> dict:
        """GET /select, or a form POST when the parameters are too long for a URL."""
        if post:
            response = self.client.post(f"{self.base_url}/select", data={**params, "wt": "json"})
        else:
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

    @staticmethod
    def _owned_delete_query(user_id: str, clause: str) -> str:
        return f'user_id:"{_escape_phrase(_require_user(user_id))}" AND {clause}'

    # ---- writes -------------------------------------------------------------

    def upsert_page_chunks(self, page_id: str, docs: list[dict], user_id: str) -> None:
        """Replace a page's chunks without a window where the page has none.

        Chunk ids are deterministic, so adding overwrites existing chunks in place.
        Any stale chunks beyond the new count are then deleted. Both requests use
        commitWithin instead of an explicit commit.
        """
        _require_user(user_id)
        if any(doc.get("user_id") != user_id or doc.get("page_id") != page_id for doc in docs):
            raise ValueError("Every chunk must belong to the given user and page")
        self._update(docs)
        stale = self._owned_delete_query(
            user_id, f'page_id:"{_escape_phrase(page_id)}" AND chunk_id:[{len(docs)} TO *]'
        )
        self._update({"delete": {"query": stale}})

    def delete_page(self, page_id: str, user_id: str) -> None:
        """Delete every chunk of one of the user's pages."""
        query = self._owned_delete_query(user_id, f'page_id:"{_escape_phrase(page_id)}"')
        self._update({"delete": {"query": query}})

    def delete_user(self, user_id: str) -> None:
        """Delete every chunk owned by user_id."""
        self._update({"delete": {"query": user_filter(user_id)}})

    # ---- reads --------------------------------------------------------------

    def bm25_search(self, query: str, user_id: str, rows: int = 30,
                    page_ids: list[str] | None = None, filters: list[str] | None = None) -> list[dict]:
        """BM25 search on text and title fields, within one user's chunks
        (and, if given, only within `page_ids` and matching every one of `filters`).
        Returns list of chunk docs (CHUNK_FIELDS) with score.
        """
        filters = [user_filter(user_id)] + ([page_ids_filter(page_ids)] if page_ids is not None else []) \
            + list(filters or [])
        params = {
            "q": sanitize_query(query),
            "defType": "edismax",
            "qf": "title^2 text",
            "pf": "text^2 title^3",
            "uf": "-*",
            "fq": filters,
            "fl": CHUNK_FIELDS + ",score",
            "rows": rows,
        }
        try:
            data = self._select(params, post=page_ids is not None)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 400:
                raise
            # Query syntax Solr couldn't parse: search for the same words as plain text.
            data = self._select({**params, "q": escape_query(params["q"])}, post=page_ids is not None)
        docs = data.get("response", {}).get("docs", [])
        return [normalize_solr_doc(doc) for doc in docs]

    def recent_pages(self, user_id: str, filters: list[str], rows: int = 30,
                     near: str | None = None) -> list[dict]:
        """The user's pages (chunk 0) matching `filters`, newest first, or nearest
        first to `near` (a Solr date). For searches that only say where or when
        ("my reddit saves", "what I read yesterday")."""
        if near is not None and not _SOLR_DATE.match(near):
            raise ValueError("near must be a Solr date")
        data = self._select({
            "q": "*:*",
            "fq": [user_filter(user_id), "chunk_id:0"] + list(filters),
            "fl": CHUNK_FIELDS,
            "sort": f"abs(ms(timestamp,{near})) asc, id asc" if near else "timestamp desc, id asc",
            "rows": rows,
        })
        return [normalize_solr_doc(d) for d in data.get("response", {}).get("docs", [])]

    def list_domains(self, user_id: str) -> list[tuple[str, int]]:
        """The sites the user has saved pages from: (domain, pages), most pages first."""
        data = self._select({
            "q": "*:*",
            "fq": [user_filter(user_id), "chunk_id:0"],
            "rows": 0,
            "facet": "true",
            "facet.field": "domain",
            "facet.limit": 2000,
            "facet.mincount": 1,
        })
        flat = data.get("facet_counts", {}).get("facet_fields", {}).get("domain", [])
        return list(zip(flat[::2], flat[1::2]))

    def knn_search(self, vector: list[float], user_id: str, k: int = 30,
                   page_ids: list[str] | None = None, filters: list[str] | None = None) -> list[dict]:
        """Dense vector KNN search within one user's chunks.

        The user filter (and optional page filter) goes in `filter`; with knn as
        the main query Solr applies it as a pre-filter, so the user gets up to k
        of their own chunks.
        """
        url = f"{self.base_url}/select"
        vector_str = "[" + ",".join(str(v) for v in vector) + "]"
        extra_filters, filters = filters, [user_filter(user_id)]
        if page_ids is not None:
            filters.append(page_ids_filter(page_ids))
        filters += list(extra_filters or [])
        payload = {
            "query": f"{{!knn f=embedding topK={k}}}{vector_str}",
            "filter": filters,
            "fields": CHUNK_FIELDS + ",score",
            "limit": k
        }
        response = self.client.post(url, json=payload, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        data = response.json()
        docs = data.get("response", {}).get("docs", [])
        return [normalize_solr_doc(doc) for doc in docs]

    def get_page_head(self, page_id: str, user_id: str) -> dict | None:
        """First chunk (chunk_id 0) of one of the user's pages, which carries the page's metadata."""
        data = self._select({
            "q": term_query("page_id", page_id),
            "fq": [user_filter(user_id), "chunk_id:0"],
            "fl": CHUNK_FIELDS,
            "rows": 1,
        })
        docs = data.get("response", {}).get("docs", [])
        return normalize_solr_doc(docs[0]) if docs else None

    def get_page_vector(self, page_id: str, user_id: str) -> list[float] | None:
        """The page vector stored on chunk 0, or None (not backfilled yet)."""
        data = self._select({
            "q": term_query("page_id", page_id),
            "fq": [user_filter(user_id), "chunk_id:0"],
            "fl": "page_embedding",
            "rows": 1,
        })
        docs = data.get("response", {}).get("docs", [])
        vector = docs[0].get("page_embedding") if docs else None
        return [float(x) for x in vector] if vector else None

    def related_pages(self, vector: list[float], user_id: str, exclude_page_id: str, k: int = 5) -> list[dict]:
        """KNN over page vectors, pre-filtered to the user's other pages."""
        vector_str = "[" + ",".join(str(v) for v in vector) + "]"
        payload = {
            "query": f"{{!knn f=page_embedding topK={k}}}{vector_str}",
            "filter": [user_filter(user_id), "-" + term_query("page_id", exclude_page_id)],
            "fields": CHUNK_FIELDS + ",score",
            "limit": k,
        }
        response = self.client.post(f"{self.base_url}/select", json=payload,
                                    headers={"Content-Type": "application/json"})
        response.raise_for_status()
        return [normalize_solr_doc(d) for d in response.json().get("response", {}).get("docs", [])]

    def scan_page_heads(self, user_id: str, fields: str, limit: int, rows: int = 500):
        """The user's pages (chunk 0 of each), newest first, at most `limit`."""
        yielded = 0
        cursor = "*"
        while yielded < limit:
            data = self._select({
                "q": "*:*",
                "fq": [user_filter(user_id), "chunk_id:0"],
                "fl": fields,
                "rows": min(rows, limit - yielded),
                "sort": "timestamp desc, id asc",
                "cursorMark": cursor,
            })
            docs = data.get("response", {}).get("docs", [])
            for doc in docs:
                yield normalize_solr_doc(doc)
            yielded += len(docs)
            next_cursor = data.get("nextCursorMark")
            if not docs or not next_cursor or next_cursor == cursor:
                return
            cursor = next_cursor

    def get_chunks_by_page_id(self, page_id: str, user_id: str) -> list[dict]:
        """Fetch all chunks for one of the user's pages, in order."""
        data = self._select({
            "q": term_query("page_id", page_id),
            "fq": user_filter(user_id),
            "fl": CHUNK_FIELDS,
            "rows": 1000,
            "sort": "chunk_id asc",
        })
        return [normalize_solr_doc(doc) for doc in data.get("response", {}).get("docs", [])]

    def count_pages(self, user_id: str) -> int:
        """How many pages the user has saved."""
        return self.list_pages(user_id, limit=0)[0]

    def list_pages(self, user_id: str, limit: int = 20, offset: int = 0) -> tuple[int, list[dict]]:
        """The user's pages (one doc per page, chunk 0), newest first: (total, docs)."""
        data = self._select({
            "q": "*:*",
            "fq": [user_filter(user_id), "chunk_id:0"],
            "fl": CHUNK_FIELDS,
            "sort": "timestamp desc, id asc",
            "start": offset,
            "rows": limit,
        })
        response = data.get("response", {})
        return response.get("numFound", 0), [normalize_solr_doc(d) for d in response.get("docs", [])]

    def _scan(self, fields: str, query: str, filters: list[str], rows: int):
        cursor = "*"
        while True:
            params = {
                "q": query,
                "fl": fields,
                "rows": rows,
                "sort": "id asc",
                "cursorMark": cursor,
            }
            if filters:
                params["fq"] = filters
            data = self._select(params)
            for doc in data.get("response", {}).get("docs", []):
                yield normalize_solr_doc(doc)
            next_cursor = data.get("nextCursorMark")
            if not next_cursor or next_cursor == cursor:
                return
            cursor = next_cursor

    def scan(self, fields: str, user_id: str, rows: int = 500):
        """Yield every chunk the user owns, paging with cursorMark (sorted by id)."""
        return self._scan(fields, "*:*", [user_filter(user_id)], rows)

    def scan_unscoped(self, fields: str, rows: int = 500, filters: list[str] | None = None):
        """Yield every document in the core. Only for maintenance scripts
        (re-index, backfill); never call this from the API."""
        return self._scan(fields, "*:*", list(filters or []), rows)


# Module-level singleton
_client = None

def get_solr_client() -> SolrClient:
    global _client
    if _client is None:
        _client = SolrClient()
    return _client
