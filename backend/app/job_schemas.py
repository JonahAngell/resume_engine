from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AddedRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group: Literal["required", "preferred"]
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter a requirement.")
        return value


class KeywordReview(BaseModel):
    model_config = ConfigDict(extra="ignore")
    dismissed: list[str] = []
    added: list[AddedRequirement] = []
    matched: list[str] = []


class JobDescriptionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str = Field(default="", max_length=200)
    role: str = Field(default="", max_length=200)
    title: str = Field(default="", max_length=300)
    body: str = Field(min_length=1, max_length=50000)
    composition_id: UUID | None = None
    keyword_review: KeywordReview | None = None

    @field_validator("company", "role", "title")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("body")
    @classmethod
    def body_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter a job description.")
        return value


class JobDescriptionRecord(BaseModel):
    id: UUID
    company: str
    role: str
    title: str
    body: str
    composition_id: UUID | None
    keyword_review: KeywordReview = Field(default_factory=KeywordReview)
    salary: str = ""
    locations: list[str] = []
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RequirementKeyword(BaseModel):
    keyword: str
    found: bool
    where: str = ""


class TagSuggestion(BaseModel):
    keyword: str
    bullet_id: str | None = None
    bullet_excerpt: str = ""
    section: str = ""
    suggestion: str
    line_id: str = ""


class RequirementRow(BaseModel):
    text: str
    group: str
    kind: str = "skill"
    label: str = ""
    matched: bool
    manual: bool = False
    detail: str = ""
    keywords: list[RequirementKeyword]
    suggestions: list[TagSuggestion]


class AnalysisRow(BaseModel):
    text: str
    kind: str = "skill"
    label: str = ""
    keywords: list[str]


class JobAnalysis(BaseModel):
    required: list[AnalysisRow]
    preferred: list[AnalysisRow]


class JobMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    composition_id: UUID


class JobMatch(BaseModel):
    composition_id: UUID
    required_count: int
    required_matched: int
    preferred_count: int
    preferred_matched: int
    required: list[RequirementRow]
    preferred: list[RequirementRow]
    salary: str = ""
    locations: list[str] = []
