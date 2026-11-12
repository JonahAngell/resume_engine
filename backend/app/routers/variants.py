"""Skill group and interest variant routes: library management and per-resume choice."""

from uuid import UUID
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError
from ..api_common import found, owner, state
from ..database import connection
from ..editing_schemas import (
    InterestSaveChoice,
    InterestVariantWrite,
    CompositionState,
    ItemVariantPick,
    ToolGroupSaveChoice,
    ToolGroupVariantWrite,
)
from ..identity import CurrentUser, resolve_current_user
from .. import skill_interest_variants as variants

router = APIRouter()

def _raise(error):
    if error == "missing":
        raise HTTPException(404, "Not found")
    if error == "name":
        raise HTTPException(409, "A variant with that name already exists")
    if error == "tools":
        raise HTTPException(422, "Variants can only use the group's own active tools")
    if error == "archived":
        raise HTTPException(409, "Restore this variant before using it")
    if error == "stale":
        raise HTTPException(409, "Composition changed; reload before saving")
    raise HTTPException(400, error)


def _payload(kind, body):
    schema = ToolGroupVariantWrite if kind == "tool_group" else InterestVariantWrite
    try:
        return schema.model_validate(body).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_context=False))


async def _add(kind, item_id, body, identity):
    data = _payload(kind, body)
    needed = ("name", "group_name") if kind == "tool_group" else ("name", "body")
    if any(not data.get(key) for key in needed):
        raise HTTPException(422, f"{' and '.join(needed)} are required")
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await variants.create_variant(c, u["id"], kind, item_id, data)
        if error:
            _raise(error)
        return row


async def _edit(kind, variant_id, body, identity):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await variants.update_variant(c, u["id"], kind, variant_id, _payload(kind, body))
        if error:
            _raise(error)
        return row


async def _archive(kind, variant_id, archived, identity):
    async with connection() as c:
        u = await owner(identity, c)
        row = await variants.set_archived(c, u["id"], kind, variant_id, archived)
        return found(row, "Variant not found")


def _library_routes(kind, parent, segment):
    @router.post(f"/api/library/{parent}/{{item_id}}/variants", status_code=201)
    async def add(item_id: UUID, req: dict = Body(...), identity: CurrentUser = Depends(resolve_current_user)):
        return await _add(kind, item_id, req, identity)

    @router.put(f"/api/library/{segment}/{{variant_id}}")
    async def edit(variant_id: UUID, req: dict = Body(...), identity: CurrentUser = Depends(resolve_current_user)):
        return await _edit(kind, variant_id, req, identity)

    @router.post(f"/api/library/{segment}/{{variant_id}}/archive")
    async def archive(variant_id: UUID, identity: CurrentUser = Depends(resolve_current_user)):
        return await _archive(kind, variant_id, True, identity)

    @router.post(f"/api/library/{segment}/{{variant_id}}/restore")
    async def restore(variant_id: UUID, identity: CurrentUser = Depends(resolve_current_user)):
        return await _archive(kind, variant_id, False, identity)

    for route in (add, edit, archive, restore):
        route.__name__ = f"{route.__name__}_{kind}_variant"


_library_routes("tool_group", "tool-groups", "tool-group-variants")
_library_routes("interest", "interests", "interest-variants")


@router.put("/api/compositions/{cid}/item-variant", response_model=CompositionState)
async def pick_item_variant(
    cid: UUID, req: ItemVariantPick, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await variants.pick_variant(
            c, u["id"], cid, req.revision, req.section, req.item_id, req.variant_id
        )
        if error:
            _raise(error)
        return state(row)


@router.post("/api/compositions/{cid}/tool-groups/{group_id}/save", response_model=CompositionState)
async def save_tool_group_choice(
    cid: UUID,
    group_id: UUID,
    req: ToolGroupSaveChoice,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await variants.save_tool_group(
            c, u["id"], cid, group_id, req.revision, req.mode, req.group_name, req.name
        )
        if error:
            _raise(error)
        return state(row)


@router.post("/api/compositions/{cid}/interests/{interest_id}/save", response_model=CompositionState)
async def save_interest_choice(
    cid: UUID,
    interest_id: UUID,
    req: InterestSaveChoice,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await variants.save_interest(
            c, u["id"], cid, interest_id, req.revision, req.mode, req.body, req.name
        )
        if error:
            _raise(error)
        return state(row)
