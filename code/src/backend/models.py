from typing import Optional, List, Union
from pydantic import BaseModel, Field

class MemoryInput(BaseModel):
    url: str
    title: str
    content: str

class SearchInput(BaseModel):
    query: str
    num_results: int = Field(default=5, ge=1, le=20)
    summarize: bool = Field(default=True)
    debug: bool = Field(default=False)

class MemoryMetadata(BaseModel):
    url: str
    title: str
    id: str
    chunks: int
    timestamp: str

class MemoryResponse(BaseModel):
    success: bool
    message: str
    metadata: MemoryMetadata

class SearchResultItem(BaseModel):
    rank: int
    id: str
    title: str
    url: str
    domain: str
    timestamp: str
    summary: Optional[str] = None

class DebugSearchResultItem(SearchResultItem):
    bm25_score: float
    vector_score: float
    fused_score: float

class SearchResponse(BaseModel):
    query: str
    results: List[Union[SearchResultItem, DebugSearchResultItem]]


SearchResult = SearchResultItem

class HealthResponse(BaseModel):
    status: str
    solr: bool
    embedding_model: bool
    gemini: bool


class SummarizeInput(BaseModel):
    query: str
    id: str


class SummarizeResponse(BaseModel):
    id: str
    summary: Optional[str] = None
