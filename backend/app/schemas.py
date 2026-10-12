


from typing import Literal
from pydantic import BaseModel, ConfigDict


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
    bullets: list[str] = []


class ToolGroup(BaseModel):
    id: str | None = None
    name: str
    items: list[str]
    bullets: list[str] = []


class Project(BaseModel):
    id: str | None = None
    name: str
    subtitle: str = ""
    date: str = ""
    bullets: list[str]


class Experience(BaseModel):
    id: str | None = None
    organization: str
    location: str = ""
    title: str
    date: str = ""
    bullets: list[str]


class CustomEntry(BaseModel):
    id: str | None = None
    primary_text: str
    secondary_text: str | None = None
    location: str | None = None
    date: str | None = None
    bullets: list[str] = []


class CustomSection(BaseModel):
    id: str | None = None
    title: str
    layout: Literal["list", "compact", "dated", "experience"] = "list"
    entries: list[CustomEntry] = []


class Resume(BaseModel):
    model_config = ConfigDict(extra="forbid")
    header: Header
    summary: str = ""
    education: list[Education] = []
    tool_groups: list[ToolGroup] = []
    projects: list[Project] = []
    work_experience: list[Experience] = []
    leadership: list[Experience] = []
    personal_interests: list[str] = []
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
    custom_sections: list[CustomSection] = []
