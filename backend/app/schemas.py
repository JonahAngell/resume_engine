


from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(max_length=5000)]
Bullets = Annotated[list[Text], Field(max_length=200)]


class Header(BaseModel):
    name: str
    phone: str = ""
    email: str = ""
    linkedin_label: str = ""
    linkedin_url: str = ""


class Education(BaseModel):
    id: str | None = None
    institution: str
    location: str = ""
    degree: str = ""
    graduation_date: str = ""
    bullets: Bullets = []


class ToolGroup(BaseModel):
    id: str | None = None
    name: str
    items: Annotated[list[Text], Field(max_length=500)]
    bullets: Bullets = []


class Project(BaseModel):
    id: str | None = None
    name: str
    subtitle: str = ""
    date: str = ""
    bullets: Bullets


class Experience(BaseModel):
    id: str | None = None
    organization: str
    location: str = ""
    title: str
    date: str = ""
    bullets: Bullets


class CustomEntry(BaseModel):
    id: str | None = None
    primary_text: str
    secondary_text: str | None = None
    location: str | None = None
    date: str | None = None
    bullets: Bullets = []


class CustomSection(BaseModel):
    id: str | None = None
    title: str
    layout: Literal["list", "compact", "dated", "experience"] = "list"
    entries: Annotated[list[CustomEntry], Field(max_length=300)] = []


class Resume(BaseModel):
    model_config = ConfigDict(extra="forbid")
    header: Header
    summary: Annotated[str, StringConstraints(max_length=20000)] = ""
    education: Annotated[list[Education], Field(max_length=300)] = []
    tool_groups: Annotated[list[ToolGroup], Field(max_length=300)] = []
    projects: Annotated[list[Project], Field(max_length=300)] = []
    work_experience: Annotated[list[Experience], Field(max_length=300)] = []
    leadership: Annotated[list[Experience], Field(max_length=300)] = []
    personal_interests: Annotated[list[Text], Field(max_length=200)] = []
    personal_interest_items: list[dict] = []
    interest_bullets: dict[str, list[str]] = {}
    section_order: list[str] = [
        "summary",
        "education",
        "tools",
        "projects",
        "work_experience",
        "leadership",
        "personal_interests",
    ]
    interest_layout: Literal["compact", "lines"] = "compact"
    custom_sections: Annotated[list[CustomSection], Field(max_length=300)] = []
