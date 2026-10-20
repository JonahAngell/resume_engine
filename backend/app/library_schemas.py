

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CurrentUserResponse(BaseModel):
    id: UUID
    external_id: str
    username: str
    display_name: str
    email: str | None


class SeedImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seed_key: str = "nia-calder-resume-v1"


class SeedImportResponse(BaseModel):
    imported: bool
    composition_id: UUID


class ProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    phone: str = ""
    email: str = ""
    linkedin_label: str = ""
    linkedin_url: str = ""

    @field_validator("email")
    @classmethod
    def email_shape(cls, value: str) -> str:
        value = value.strip()
        if value and ("@" not in value or value.startswith("@") or value.endswith("@")):
            raise ValueError("Enter a valid email address.")
        return value

    @field_validator("linkedin_url")
    @classmethod
    def url_shape(cls, value: str) -> str:
        value = value.strip()
        if value and not value.lower().startswith(("http://", "https://")):
            raise ValueError("LinkedIn URL must start with http:// or https://.")
        return value


class SummaryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1)


class EducationWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    institution: str = Field(min_length=1)
    college_school: str = ""
    location: str = ""
    degree_type: str = ""
    degree_major: str = ""
    graduation_year: int | None = Field(default=None, ge=1900, le=2200)
    graduation_month: int | None = Field(default=None, ge=1, le=12)
    display_date: str = ""


class InterestWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1)


class ReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[UUID]


class CompositionSummarySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    summary_variant_id: UUID | None


class CompositionProfileSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    profile_id: UUID


class ProfileDuplicate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=120)


class CompositionInterestSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    interest_id: UUID
    included: bool


class CompositionSummary(BaseModel):
    id: UUID
    name: str
    description: str = ""
    display_title: str = ""
    target_company: str = ""
    target_role: str = ""
    job_description_id: UUID | None = None
    profile_id: UUID | None = None
    archived_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    autosaved_at: datetime | None = None
    revision: int = 1


class LibraryResponse(BaseModel):
    default_sets: list[dict] = []
    default_set_members: list[dict] = []
    profiles: list[dict] = []
    summary_variants: list[dict]
    education: list[dict]
    tool_groups: list[dict]
    projects: list[dict]
    employment: list[dict]
    leadership: list[dict]
    interests: list[dict]
    custom_sections: list[dict] = []
    compositions: list[CompositionSummary]
    composition_bullets: list[dict] = []
    composition_items: list[dict] = []
    composition_custom_sections: list[dict] = []


class ToolGroupWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)


class ToolWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    group_id: UUID


class ToolMoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_id: UUID


class ToolRestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: str = Field(pattern="^(require-parent|restore-parent|move)$")
    group_id: UUID | None = None


class CustomSectionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    layout: str = Field(pattern="^(list|compact|dated|experience)$")


class CustomEntryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_id: UUID
    primary_text: str = Field(min_length=1)
    secondary_text: str = ""
    location: str = ""
    date_label: str = ""


class CompositionSectionsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    section_order: list[str]
    interest_layout: str = Field(pattern="^(compact|lines)$")
    included_builtin: list[str]
    included_custom: list[UUID]



class CompositionItemOrderWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    section: str
    ids: list[UUID]

class LibraryItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1)
    section: str = Field(pattern="^(experience|projects|education|leadership|skills|interests|custom)$")
    parent_context: str = Field(default="", max_length=300)
    variant_name: str = Field(default="Default", min_length=1, max_length=120)
    tags: list[str] = []
class LibraryTagsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    names: list[str]
class LibraryBulkWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[UUID]
    action: str = Field(pattern="^(archive|restore|add-tags|remove-tags|move-section)$")
    tag_names: list[str] = []
    section: str | None = None

class LibraryParentWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_id: UUID | None = None
    parent_type: str | None = Field(default=None, pattern="^(content_item|education_item|tool_group|interest|custom_entry)$")
