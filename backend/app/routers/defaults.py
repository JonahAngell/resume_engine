"""Defaults API routes."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from ..database import (
    connection,
)
from ..editing_schemas import (
    DefaultSetArchive,
    DefaultSetBulk,
    DefaultSetFromComposition,
    DefaultSetMembershipsWrite,
    DefaultSetWrite,
)
from .. import default_sets
from ..identity import CurrentUser, resolve_current_user
from ..api_common import found, owner

router = APIRouter()


@router.get("/api/default-sets")
async def list_default_sets(identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        return {
            "sets": await default_sets.list_sets(c, u["id"], include_archived=True),
            "members": await default_sets.list_members(c, u["id"]),
        }


@router.post("/api/default-sets", status_code=201)
async def create_default_set(req: DefaultSetWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await default_sets.create_set(c, u["id"], req.name, req.description)
        if error == "name":
            raise HTTPException(409, "A defaults set with that name already exists")
        return row


@router.put("/api/default-sets/memberships")
async def save_default_set_memberships(
    req: DefaultSetMembershipsWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        try:
            rows = await default_sets.set_memberships(
                c,
                u["id"],
                req.item_type,
                req.item_id,
                [(m.set_id, m.variant_id) for m in req.memberships],
            )
        except ValueError as exc:
            raise HTTPException(404, str(exc))
        if rows is None:
            raise HTTPException(404, "Defaults set not found")
        return rows


@router.put("/api/default-sets/{set_id}")
async def update_default_set(set_id: UUID, req: DefaultSetWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await default_sets.update_set(c, u["id"], set_id, req.name, req.description)
        if error == "name":
            raise HTTPException(409, "A defaults set with that name already exists")
        return found(row, "Defaults set not found")


@router.post("/api/default-sets/{set_id}/archive")
async def archive_default_set(set_id: UUID, req: DefaultSetArchive, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await default_sets.archive_set(c, u["id"], set_id, req.archived)
        if error == "name":
            raise HTTPException(409, "An active defaults set already uses that name")
        return found(row, "Defaults set not found")


@router.post("/api/default-sets/{set_id}/default")
async def make_default_set(set_id: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row = await default_sets.set_default(c, u["id"], set_id)
        return found(row, "Defaults set not found")


@router.post("/api/default-sets/{set_id}/bulk")
async def bulk_default_set(set_id: UUID, req: DefaultSetBulk, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row = await default_sets.bulk_bullets(c, u["id"], set_id, req.action, req.bullet_ids)
        return found(row, "Defaults set not found")


@router.post("/api/compositions/{cid}/default-set", status_code=201)
async def save_default_set_from_resume(
    cid: UUID, req: DefaultSetFromComposition, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await default_sets.save_from_composition(c, u["id"], cid, req.name, req.replace_id)
        if error == "name":
            raise HTTPException(409, "A defaults set with that name already exists")
        if not row:
            raise HTTPException(404, "Resume or defaults set not found")
        return row
