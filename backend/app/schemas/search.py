from __future__ import annotations

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    max_results: int = Field(default=5, ge=1, le=20)


class SearchResultRecord(BaseModel):
    title: str
    url: str
    snippet: str


class SearchResponse(BaseModel):
    query: str
    provider: str
    results: list[SearchResultRecord]
    count: int
