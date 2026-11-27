from typing import Literal, Optional, List, Union, Dict
from pydantic import BaseModel, Field

class YouTubeInput(BaseModel):
    """A YouTube video's details, fetched by the extension in the user's browser
    (YouTube blocks transcript requests from the server)."""
    transcript: Optional[str] = Field(default=None, max_length=500_000)
    language: Optional[str] = Field(default=None, max_length=20)
    title: Optional[str] = Field(default=None, max_length=500)
    channel: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10_000)
    duration_seconds: Optional[int] = Field(default=None, ge=0, le=1_000_000)


class MemoryInput(BaseModel):
    url: str = Field(max_length=2048)
    # A page without a title sends its URL instead; ingest shortens it to 500.
    title: str = Field(max_length=2048)
    content: str = Field(max_length=500_000)
    html: Optional[str] = Field(default=None, max_length=3_000_000)
    canonical_url: Optional[str] = Field(default=None, max_length=2048)
    is_manual: bool = False
    youtube: Optional[YouTubeInput] = None

class SearchInput(BaseModel):
    query: str = Field(max_length=500)
    num_results: int = Field(default=10, ge=1, le=20)
    summarize: bool = Field(default=False)
    debug: bool = Field(default=False)

class PageInfo(BaseModel):
    id: str
    url: str
    title: str
    domain: str
    timestamp: str
    chunks: Optional[int] = None

class MemoryResponse(BaseModel):
    status: str  # "saved" | "unchanged" | "skipped"
    message: str
    page: Optional[PageInfo] = None

class MemoryStatusResponse(BaseModel):
    saved: bool
    page: Optional[PageInfo] = None

class ExistingPagesInput(BaseModel):
    """Page ids the extension remembers (its "Auto-saved today" list)."""
    ids: List[str] = Field(max_length=50)

class ExistingPagesResponse(BaseModel):
    """Those of the ids that are still in the caller's library."""
    ids: List[str]

class MemoriesResponse(BaseModel):
    total: int
    pages: List[PageInfo]

class SearchResultItem(BaseModel):
    rank: int
    id: str
    title: str
    url: str
    domain: str
    timestamp: str
    snippet: Optional[str] = None
    summary: Optional[str] = None

class DebugSearchResultItem(SearchResultItem):
    bm25_rank: Optional[int] = None
    knn_rank: Optional[int] = None
    fused_score: float
    rerank_score: Optional[float] = None
    vector_similarity: Optional[float] = None

class SearchResponse(BaseModel):
    query: str
    results: List[Union[DebugSearchResultItem, SearchResultItem]]
    timings: Optional[Dict[str, float]] = None


SearchResult = SearchResultItem

class HealthResponse(BaseModel):
    status: str
    solr: bool
    embedding_model: bool
    gemini: bool


class SummarizeInput(BaseModel):
    query: str = Field(max_length=500)
    id: str = Field(max_length=512)


class SummarizeResponse(BaseModel):
    id: str
    summary: Optional[str] = None


class RelatedPage(BaseModel):
    id: str
    title: str
    url: str
    domain: str
    saved_at: str
    similarity: float


class RelatedResponse(BaseModel):
    page_id: str
    related: List[RelatedPage]


class ReportContext(BaseModel):
    """What the report form shows the user before sending; nothing else is sent."""
    app_version: Optional[str] = Field(default=None, max_length=40)
    # A path only (the client drops the query string, so no search terms).
    page: Optional[str] = Field(default=None, max_length=200)
    user_agent: Optional[str] = Field(default=None, max_length=400)
    last_error: Optional[str] = Field(default=None, max_length=500)


class ReportInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    source: Literal["web", "extension"] = "web"
    context: ReportContext = Field(default_factory=ReportContext)


class ReportResponse(BaseModel):
    status: str  # "received"
    id: int


# ---- pages kept on the user's device (local-first) -------------------------------

class SearchSettingsResponse(BaseModel):
    """The numbers search runs with, so the extension's local engine uses the same."""
    DEFAULT_TOP_K: int
    DEFAULT_CANDIDATE_POOL: int
    RRF_K: int
    BM25_WEIGHT: float
    VECTOR_WEIGHT: float
    PAGE_SECOND_CHUNK_WEIGHT: float
    MIN_VECTOR_SIMILARITY: float
    KEYWORD_FULL_MATCH: float
    QUERY_INTENT_ENABLED: bool
    INTENT_WEIGHT: float
    CHUNK_MAX_WORDS: int
    CHUNK_MIN_WORDS: int
    CHUNK_OVERLAP_WORDS: int
    MAX_PAGES_PER_USER: int
    EMBEDDING_MODEL: str
    EMBEDDING_DIM: int
    EMBEDDING_QUERY_PREFIX: str


class MeResponse(BaseModel):
    library_id: str
    device_key: str  # base64url, for encrypting the extension's local copy at rest


class TransferInput(BaseModel):
    """A page moving from the extension's local store to the server, with the
    chunks and details it was first saved with."""
    url: str = Field(max_length=2048)
    title: str = Field(max_length=2048)
    chunks: List[str] = Field(min_length=1, max_length=5000)
    description: str = Field(default="", max_length=2000)
    timestamp: str = Field(max_length=40)
    content_hash: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class PageContentResponse(BaseModel):
    id: str
    url: str
    title: str
    description: str
    timestamp: str
    content_hash: str
    chunks: List[str]


class SummarizeTextInput(BaseModel):
    """A summary of a page kept on the device: its text is sent for this one request."""
    query: str = Field(max_length=500)
    title: str = Field(default="", max_length=2048)
    text: str = Field(max_length=200_000)


class BackupInfoResponse(BaseModel):
    bytes: int
    sha256: str
    updated_at: float
