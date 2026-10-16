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


class Evidence(BaseModel):
    source_requirement: str
    matched_text: str = ""
    relation: str
    section: str = ""
    confidence: float
    explanation: str = ""


class RequirementKeyword(BaseModel):
    keyword: str
    found: bool
    where: str = ""
    relation: str = ""
    evidence: Evidence | None = None


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
    section: str = ""
    category: str = ""
    weight: float = 1.0
    match_mode: Literal["any", "all"] = "all"
    matched: bool
    manual: bool = False
    detail: str = ""
    keywords: list[RequirementKeyword]
    suggestions: list[TagSuggestion]


class AnalysisRow(BaseModel):
    text: str
    kind: str = "skill"
    label: str = ""
    match_mode: Literal["any", "all"] = "all"
    keywords: list[str]
    category: str = ""
    section: str = ""
    weight: float = 0


class JobAnalysis(BaseModel):
    required: list[AnalysisRow]
    preferred: list[AnalysisRow]
    responsibilities: list[AnalysisRow] = []
    eligibility: list[AnalysisRow] = []


class ScoreComponents(BaseModel):
    required_coverage: float = 0
    preferred_coverage: float = 0
    responsibility_alignment: float = 0
    domain_alignment: float = 0
    tools_alignment: float = 0
    evidence_quality: float = 0


class EligibilityGate(BaseModel):
    status: Literal["pass", "fail", "unknown", "not_stated"] = "not_stated"
    detail: str = ""


class Eligibility(BaseModel):
    degree: EligibilityGate = EligibilityGate()
    years: EligibilityGate = EligibilityGate()
    certification: EligibilityGate = EligibilityGate()
    schedule: EligibilityGate = EligibilityGate()
    travel: EligibilityGate = EligibilityGate()
    work_location: EligibilityGate = EligibilityGate()
    employment_type: EligibilityGate = EligibilityGate()


class JobFamily(BaseModel):
    id: str
    label: str
    confidence: float


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
    responsibilities: list[RequirementRow] = []
    eligibility_rows: list[RequirementRow] = []
    salary: str = ""
    locations: list[str] = []
    scores: ScoreComponents = ScoreComponents()
    eligibility: Eligibility = Eligibility()
    families: list[JobFamily] = []
