from __future__ import annotations

from pydantic import BaseModel


class LanguageCapability(BaseModel):
    id: str
    name: str
    notes: str


class CodingBotCapabilities(BaseModel):
    slug: str
    name: str
    sector: str
    languages: list[LanguageCapability]
    logic_capabilities: list[str]
    build_capabilities: list[str]
    trained_skills: list[str]
    browser_ui: str
