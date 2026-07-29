from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class WebCaptureRequest(BaseModel):
    url: HttpUrl
    max_images: int = Field(default=8, ge=0, le=20)


class WebCaptureRecord(BaseModel):
    id: int
    url: str
    title: str
    summary: str
    text_chars: int
    image_count: int
    compressed_bytes: int
    storage_path: str
    created_at: str


class WebCaptureDetail(BaseModel):
    id: int
    url: str
    title: str
    text: str
    text_chars: int
    image_count: int
    compressed_bytes: int
    storage_path: str
    images: list[dict]
    created_at: str


class WebCaptureResponse(BaseModel):
    capture_id: int
    url: str
    title: str
    text_chars: int
    image_count: int
    compressed_bytes: int
    summary: str
    message: str


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    engine: str | None = Field(default=None, pattern=r"^(duckduckgo|bing)$")
    limit: int = Field(default=5, ge=1, le=10)
    auto_capture_top: bool = False


class WebSearchResultItem(BaseModel):
    title: str
    url: str
    snippet: str


class WebSearchResponse(BaseModel):
    search_id: int
    engine: str
    query: str
    result_count: int
    compressed_bytes: int
    results: list[WebSearchResultItem]
    message: str


class WebAssistRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    requesting_bot: str = Field(default="master-bot", max_length=64)
