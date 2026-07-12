from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SkillCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    description: str = ""
    instructions: str = Field(min_length=1)
    parameters_schema: dict = Field(default_factory=dict)


class SkillRecord(BaseModel):
    id: int
    slug: str
    name: str
    category: str
    description: str
    instructions: str
    parameters_schema: dict
    created_at: datetime


class SkillLearnRequest(BaseModel):
    skill_slug: str = Field(min_length=1)
    parameters: dict = Field(default_factory=dict)


class SkillAssignmentRecord(BaseModel):
    id: int
    skill_slug: str
    skill_name: str
    category: str
    status: str
    parameters: dict
    instructions: str
    learned_at: datetime
    activated_at: datetime | None = None


class SkillAssignmentUpdate(BaseModel):
    status: str | None = Field(None, pattern=r"^(learning|active|paused)$")
    parameters: dict | None = None
