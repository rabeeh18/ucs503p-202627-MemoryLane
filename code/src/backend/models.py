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
    # A topic id from GET /map: search only that topic's pages.
    topic: Optional[str] = Field(default=None, max_length=64)

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


class MapTopicMatch(BaseModel):
    id: str
    label: str
    score: float


class MapSearchResponse(BaseModel):
    query: str
    version: Optional[str] = None
    topics: List[MapTopicMatch]
    pages: List[str]


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
