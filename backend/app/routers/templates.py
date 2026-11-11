"""Custom resume templates: list, create, edit, delete, and preview a draft on a resume."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .. import templates_repository as templates
from ..api_common import owner, state
from ..database import connection
from ..editing_schemas import TemplateStyle
from ..identity import CurrentUser, resolve_current_user
from ..library_repository import load_composition
from ..phase2m_repository import materialize_composition
from ..render import render_resume
from ..template_settings import options, strict_settings

router = APIRouter()


class TemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    base_style: TemplateStyle
    settings: dict | None = None


class TemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=80)
    settings: dict
    # The resume open in the editor: its new revision comes back so the editor stays current.
    composition_id: UUID | None = None


class TemplatePreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    composition_id: UUID
    base_style: TemplateStyle
    settings: dict


def _checked(base_style: str, settings: dict | None) -> dict:
    try:
        return strict_settings(base_style, settings)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first.get("loc", ()))
        raise HTTPException(422, f"{where}: {first.get('msg')}" if where else first.get("msg")) from exc


async def _composition_state(c, user_id, composition_id):
    if not composition_id:
        return None
    row = await load_composition(c, user_id, composition_id)
    return state(row) if row else None


@router.get("/api/templates")
async def list_templates(identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        return {"templates": await templates.list_templates(c, u["id"]), "options": options()}


@router.post("/api/templates", status_code=201)
async def create_template(req: TemplateCreate, identity: CurrentUser = Depends(resolve_current_user)):
    settings = _checked(req.base_style, req.settings)
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await templates.create_template(c, u["id"], req.name, req.base_style, settings)
    if error == "name":
        raise HTTPException(409, "You already have a template with that name")
    return row


@router.put("/api/templates/{template_id}")
async def update_template(template_id: UUID, req: TemplateUpdate, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        current = await templates.get_template(c, u["id"], template_id)
        if not current:
            raise HTTPException(404, "Template not found")
        settings = _checked(current["base_style"], req.settings)
        row, error = await templates.update_template(c, u["id"], template_id, req.revision, req.name, settings)
        if error == "missing":
            raise HTTPException(404, "Template not found")
        if error == "stale":
            raise HTTPException(409, "This template changed elsewhere. Reload it, then try again.")
        if error == "name":
            raise HTTPException(409, "You already have a template with that name")
        return {"template": row, "composition": await _composition_state(c, u["id"], req.composition_id)}


@router.delete("/api/templates/{template_id}")
async def delete_template(
    template_id: UUID,
    composition_id: UUID | None = Query(default=None),
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        if await templates.delete_template(c, u["id"], template_id) == "missing":
            raise HTTPException(404, "Template not found")
        return {"composition": await _composition_state(c, u["id"], composition_id)}


@router.post("/api/templates/preview", response_class=HTMLResponse)
async def preview_template(req: TemplatePreview, identity: CurrentUser = Depends(resolve_current_user)):
    """One resume rendered with unsaved settings, for the designer's live preview."""
    settings = _checked(req.base_style, req.settings)
    async with connection() as c:
        u = await owner(identity, c)
        materialized, error = await materialize_composition(c, u["id"], req.composition_id)
    if error:
        raise HTTPException(404, "Composition not found")
    return HTMLResponse(
        render_resume(
            materialized["resume"],
            True,
            materialized["renderer_contract_version"],
            materialized.get("section_sort_modes", {}),
            materialized.get("date_format", "long"),
            req.base_style,
            materialized.get("skill_row_max", 4),
            appearance={"settings": settings, "tools_layout": None},
        )
    )
