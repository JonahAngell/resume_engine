"""Structured results for an optional OpenRouter review."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .job_schemas import JobMatch

Category = Literal[
    "tool",
    "domain",
    "responsibility",
    "methodology",
    "credential",
    "degree",
    "experience_duration",
    "soft_skill",
]

ReviewStatus = Literal["ok", "unavailable", "rate_limited", "invalid"]


class AiFamily(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: str
    confidence: float = Field(ge=0, le=1)


class AiRequirement(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    group: str
    category: Category
    source_span: str


class AiKeyword(BaseModel):
    model_config = ConfigDict(extra="ignore")
    keyword: str
    category: Category
    source_span: str


class AiSemantic(BaseModel):
    model_config = ConfigDict(extra="ignore")
    requirement: str
    resume_span: str
    section: str = ""
    confidence: float = Field(ge=0, le=1)
    rationale: str = ""


class AiBulletTags(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bullet: str
    section: str = ""
    action: str = ""
    domain: str = ""
    skill: str = ""
    tool: str = ""
    outcome: str = ""
    metric: str = ""


class AiSuggestion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    requirement: str
    resume_quote: str
    suggestion: str


class AiReview(BaseModel):
    model_config = ConfigDict(extra="ignore")
    composition_id: UUID
    status: ReviewStatus
    detail: str = ""
    model: str = ""
    match: JobMatch
    families: list[AiFamily] = []
    requirements: list[AiRequirement] = []
    keywords: list[AiKeyword] = []
    semantic_candidates: list[AiSemantic] = []
    bullet_tags: list[AiBulletTags] = []
    suggestions: list[AiSuggestion] = []
