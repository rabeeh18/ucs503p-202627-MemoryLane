from typing import Optional, List, Union, Dict
from pydantic import BaseModel, Field

class MemoryInput(BaseModel):
    url: str = Field(max_length=2048)
    title: str = Field(max_length=500)
    content: str = Field(max_length=500_000)
    html: Optional[str] = Field(default=None, max_length=3_000_000)
    canonical_url: Optional[str] = Field(default=None, max_length=2048)
    is_manual: bool = False

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
