



from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .schemas import Resume

Kind = Literal["project", "employment", "leadership"]


class HistoricalItemWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Kind
    name: str | None = None
    subtitle: str | None = None
    organization: str | None = None
    location: str | None = None
    title: str | None = None
    date_label: str = ""
    start_year: int | None = Field(default=None, ge=1900, le=2200)
    start_month: int | None = Field(default=None, ge=1, le=12)
    end_year: int | None = Field(default=None, ge=1900, le=2200)
    end_month: int | None = Field(default=None, ge=1, le=12)
    is_current: bool = False
    bullets: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_kind_and_dates(self):
        if self.kind == "project":
            self.name = (self.name or "").strip()
            if not self.name:
                raise ValueError("Project name is required.")
        else:
            self.organization = (self.organization or "").strip()
            self.title = (self.title or "").strip()
            if not self.organization or not self.title:
                raise ValueError("Organization and title are required.")
        if self.start_month and not self.start_year:
            raise ValueError("Start month requires a start year.")
        if self.end_month and not self.end_year:
            raise ValueError("End month requires an end year.")
        if self.is_current:
            self.end_year = self.end_month = None
        if self.start_year and self.end_year:
            start = (self.start_year, self.start_month or 0)
            end = (self.end_year, self.end_month or 12)
            if end < start:
                raise ValueError("End date cannot precede start date.")
        return self


class CompositionItemSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    item_id: UUID
    included: bool


class CompositionSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    resume: Resume
    source: str = "autosave"


class CompositionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str = ""
    display_title: str = Field(default="", max_length=200)
    target_company: str = Field(default="", max_length=200)
    target_role: str = Field(default="", max_length=200)
    default_set_id: UUID | None = None
    # True starts from the whole library even when a default set exists.
    entire_library: bool = False
    job_description_id: UUID | None = None


class DuplicateComposition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)


class RestoreRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)


class CompositionState(BaseModel):
    id: UUID
    name: str
    description: str = ""
    display_title: str = ""
    target_company: str = ""
    target_role: str = ""
    job_description_id: UUID | None = None
    preferred_page_length: int = 1
    date_format: str = "long"
    template_style: str = "classic"
    skill_row_max: int = 4
    section_sort_modes: dict[str, str] = {}
    summary_variant_id: UUID | None = None
    profile_id: UUID | None = None
    is_starter: bool = False
    is_default_starter: bool = False
    revision: int
    archived_at: object | None = None
    created_at: object | None = None
    updated_at: object | None = None
    autosaved_at: object | None = None
    resume: Resume


class BulletCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_id: UUID
    variant_name: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1)


class BulletMove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_id: UUID


class BulletRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_id: UUID | None = None


class VariantWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1)


class VariantArchive(BaseModel):
    model_config = ConfigDict(extra="forbid")
    replacement_variant_id: UUID | None = None


class CompositionMetadataWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    display_title: str = Field(default="", max_length=200)
    target_company: str = Field(default="", max_length=200)
    target_role: str = Field(default="", max_length=200)
    job_description_id: UUID | None = None

class CompositionLifecycleWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)



DestinationSection = Literal["projects", "work_experience", "education", "leadership", "tool_groups", "personal_interests", "custom_sections"]
DestinationParentType = Literal["content_item", "education_item", "tool_group", "interest", "custom_entry"]
class BulletPlacementWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    bullet_id: UUID
    variant_id: UUID
    destination_section: DestinationSection
    destination_parent_type: DestinationParentType
    destination_parent_id: UUID
    sort_order: int | None = Field(default=None, ge=0)
class BulletCreateAndPlace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    body: str = Field(min_length=1)
    variant_name: str = Field(default="Default", min_length=1, max_length=120)
    library_section: str = Field(pattern="^(experience|projects|education|leadership|skills|interests|custom)$")
    parent_context: str = Field(default="", max_length=300)
    destination_section: DestinationSection
    destination_parent_type: DestinationParentType
    destination_parent_id: UUID
class BulletPlacementReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    bullet_id: UUID
    variant_id: UUID
class BulletPlacementReorder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    destination_section: DestinationSection
    destination_parent_type: DestinationParentType
    destination_parent_id: UUID
    ids: list[UUID]
class ToolVisibilityWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    included: bool
class ToolOrderWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    ids: list[UUID]


class BulletUsageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)

TemplateStyle = Literal["classic", "sheets", "harvard", "dais", "sre"]


class CompositionPreferencesWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    preferred_page_length: int = Field(ge=1, le=10)
    date_format: Literal["year", "numeric", "short", "long"] = "long"
    template_style: TemplateStyle = "classic"
    skill_row_max: int = Field(default=4, ge=1, le=20)
    section_sort_modes: dict[str, Literal["automatic", "manual"]] = {}


class EntryCreateWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    section: str
    fields: dict


SaveMode = Literal["variant", "new", "overwrite"]


class BulletSaveChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    mode: SaveMode = "variant"
    body: str = Field(min_length=1)


class EntrySaveChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    mode: SaveMode = "variant"
    section: str
    fields: dict


class SummarySaveChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    mode: SaveMode = "variant"
    name: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1)


class ProfileSaveChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    mode: SaveMode = "variant"
    fields: dict


class DefaultSetFromComposition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="", max_length=120)
    replace_id: UUID | None = None

    @model_validator(mode="after")
    def named_or_replacing(self):
        if not self.replace_id and not self.name.strip():
            raise ValueError("Name the defaults set")
        return self


class DefaultSetWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


DefaultSetItemType = Literal[
    "content_item",
    "education_item",
    "tool_group",
    "interest",
    "custom_section",
    "summary",
    "profile",
    "bullet",
]


class DefaultSetMembership(BaseModel):
    model_config = ConfigDict(extra="forbid")
    set_id: UUID
    variant_id: UUID | None = None


class DefaultSetMembershipsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_type: DefaultSetItemType
    item_id: UUID
    memberships: list[DefaultSetMembership] = Field(default_factory=list, max_length=100)


class DefaultSetBulk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["add", "remove"]
    bullet_ids: list[UUID] = Field(min_length=1, max_length=500)


class DefaultSetArchive(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archived: bool = True


class AttachBulletWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_bullet_id: UUID


class SkillRecommendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keyword: str = Field(min_length=1, max_length=120)
    allow_ai: bool = False


class SkillAddWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=120)
    group_id: UUID | None = None
    new_group_name: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def one_group(self):
        if bool(self.group_id) == bool((self.new_group_name or "").strip()):
            raise ValueError("Choose a group or name a new one")
        return self


AiGoal = Literal["concise", "impact", "align", "one_line"]
AiKeywordCategory = Literal[
    "tool", "domain", "responsibility", "methodology", "credential", "degree", "experience_duration", "soft_skill", ""
]


class AiVariantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Only the one-line goal works without a job.
    job_id: UUID | None = None
    keyword: str = Field(default="", max_length=200)
    requirement: str = Field(default="", max_length=2000)
    category: AiKeywordCategory = ""
    goal: AiGoal | None = None
    incorporate_keyword: bool = False
    max_chars: int | None = Field(default=None, ge=30, le=200)

    @model_validator(mode="after")
    def job_unless_one_line(self):
        if self.job_id is None and self.goal != "one_line":
            raise ValueError("Choose a job for this suggestion")
        return self


class KeywordAssistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    keyword: str = Field(min_length=1, max_length=200)
    requirement: str = Field(default="", max_length=2000)
    category: AiKeywordCategory = ""


class KeywordDefineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keyword: str = Field(min_length=1, max_length=200)
    requirement: str = Field(default="", max_length=2000)


class KeywordBulletAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    parent_id: UUID
    body: str = Field(min_length=1, max_length=2000)
    source: Literal["draft", "edited", "own"]
    job_id: UUID | None = None
    model: str = Field(default="", max_length=200)


class AiVariantAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    name: str = Field(default="", max_length=120)
    body: str = Field(min_length=1, max_length=2000)
    source: Literal["draft", "edited", "own"]
    job_id: UUID | None = None
    model: str = Field(default="", max_length=200)


class VariantPickRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    placement_ids: list[UUID] = Field(default_factory=list, max_length=60)
    use_ai: bool = True


class CondenseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID | None = None
    # Measured in the preview, keyed by its `{parentId}-bullet-{index}` and item ids.
    bullet_lines: dict[str, int] = Field(default_factory=dict, max_length=400)
    item_lines: dict[str, int] = Field(default_factory=dict, max_length=200)
    chars_per_line: int = Field(default=0, ge=0, le=300)
    lines_over: int = Field(default=0, ge=0, le=500)
    use_ai: bool = True


class CondenseRewrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    placement_id: UUID
    body: str = Field(min_length=1, max_length=2000)
    name: str = Field(default="", max_length=120)
    source: Literal["draft", "edited"] = "draft"
    model: str = Field(default="", max_length=200)


class CondenseApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    job_id: UUID | None = None
    remove_bullets: list[UUID] = Field(default_factory=list, max_length=200)
    remove_entries: list[UUID] = Field(default_factory=list, max_length=60)
    rewrites: list[CondenseRewrite] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def something_to_apply(self):
        if not (self.remove_bullets or self.remove_entries or self.rewrites):
            raise ValueError("Choose at least one change")
        return self


class PlacementSwap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    placement_id: UUID
    bullet_id: UUID
    variant_id: UUID


class BulletPlacementReplaceMany(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    items: list[PlacementSwap] = Field(min_length=1, max_length=60)


class AtsScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    composition_id: UUID
    page_count: int | None = Field(default=None, ge=1, le=20)

