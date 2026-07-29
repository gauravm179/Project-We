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
