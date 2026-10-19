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


class VariantDraft(BaseModel):
    name: str
    body: str
    rationale: str = ""


class VariantSuggestions(BaseModel):
    status: Literal["ok", "unavailable", "rate_limited", "invalid"]
    detail: str = ""
    model: str = ""
    original: str = ""
    category: str = ""
    drafts: list[VariantDraft] = []
    dropped: int = 0
    fits: bool = True
    reason: str = ""


class KeywordRevision(BaseModel):
    id: str
    placement_id: str
    section: str = ""
    entry: str = ""
    original: str
    body: str
    rationale: str = ""


class KeywordNewBullet(BaseModel):
    id: str
    parent_id: str
    section: str
    entry: str
    body: str
    rationale: str = ""
    placeholders: bool = False


class KeywordEntry(BaseModel):
    parent_id: str
    section: str
    entry: str


class KeywordAssist(BaseModel):
    status: Literal["ok", "unavailable", "rate_limited", "invalid"]
    detail: str = ""
    model: str = ""
    revision: int = 0
    keyword: str = ""
    category: str = ""
    allowed: bool = True
    revisions: list[KeywordRevision] = []
    new_bullets: list[KeywordNewBullet] = []
    entries: list[KeywordEntry] = []
    no_fit_reason: str = ""
    dropped: int = 0


class CoachSuggestion(BaseModel):
    id: str
    kind: Literal["rewrite", "summary", "add_skill"]
    requirement: str
    group: str
    category: str = ""
    keyword: str = ""
    placement_id: str = ""
    original: str = ""
    proposed: str = ""
    rationale: str = ""
    priority: Literal["high", "medium", "low"] = "medium"


class CoachEquivalent(BaseModel):
    id: str
    requirement: str
    group: str
    placement_id: str
    bullet: str
    rationale: str = ""


class CoachResult(BaseModel):
    status: Literal["ok", "unavailable", "rate_limited", "invalid"]
    detail: str = ""
    model: str = ""
    revision: int = 0
    suggestions: list[CoachSuggestion] = []
    equivalents: list[CoachEquivalent] = []
    dropped: int = 0


class AtsComponent(BaseModel):
    id: str
    label: str
    weight: int
    earned: float
    ratio: float
    detail: str
    tips: list[str] = []


class AtsMethod(BaseModel):
    id: str
    label: str
    weight: int
    rule: str
    why: str


class AtsScore(BaseModel):
    score: int
    band: Literal["Strong", "Fair", "Needs work"]
    components: list[AtsComponent]
    methodology: list[AtsMethod]
    disclaimer: str
    revision: int = 0



class VariantPickCandidate(BaseModel):
    key: str
    bullet_id: str
    variant_id: str
    name: str = ""
    body: str
    current: bool = False
    score: int | None = None
    reason: str = ""
    keyword_hits: list[str] = []


class VariantPickSlot(BaseModel):
    placement_id: str
    parent_id: str
    section: str = ""
    parent_label: str = ""
    current_key: str
    best_key: str
    recommend: bool = False
    candidates: list[VariantPickCandidate]


class VariantPick(BaseModel):
    status: Literal["ok", "unavailable", "rate_limited", "invalid"]
    detail: str = ""
    model: str = ""
    method: Literal["ai", "keywords"] = "keywords"
    revision: int = 0
    slots: list[VariantPickSlot] = []
    dropped: int = 0
