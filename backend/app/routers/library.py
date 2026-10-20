"""Library API routes."""

import asyncio
from uuid import UUID
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from ..database import (
    connection,
)
from ..editing_repository import (
    add_item,
    archive_bullet,
    archive_variant,
    create_bullet,
    create_variant,
    duplicate_bullet,
    duplicate_variant,
    move_bullet,
    reorder_bullets,
    reorder_items,
    reorder_variants,
    restore_bullet,
    restore_variant,
    set_default_variant,
    update_item,
    update_variant,
)
from ..editing_schemas import (
    BulletCreate,
    BulletMove,
    BulletRestore,
    HistoricalItemWrite,
    VariantArchive,
    VariantWrite,
    AttachBulletWrite,
)
from ..resume_variants import (
    attach_bullet,
    detach_variant,
)
from ..identity import CurrentUser, resolve_current_user
from ..library_repository import (
    create_education,
    create_interest,
    create_profile,
    create_summary,
    duplicate_profile,
    duplicate_summary,
    fetch_library,
    reorder,
    search,
    update_profile,
    set_archive,
    update_education,
    update_interest,
    update_summary,
    create_tool_group,
    update_tool_group,
    create_tool,
    update_tool,
    reorder_tools,
    move_tool,
    restore_tool,
    create_custom_section,
    update_custom_section,
    create_custom_entry,
    update_custom_entry,
    reorder_custom_entries,
    set_custom_archive,
)
from ..library_schemas import (
    EducationWrite,
    InterestWrite,
    LibraryResponse,
    ProfileDuplicate,
    ProfileWrite,
    ReorderRequest,
    SeedImportRequest,
    SeedImportResponse,
    SummaryWrite,
    ToolGroupWrite,
    ToolWrite,
    ToolMoveRequest,
    ToolRestoreRequest,
    CustomSectionWrite,
    CustomEntryWrite,
    LibraryItemCreate, LibraryTagsWrite, LibraryBulkWrite, LibraryParentWrite,
)
from ..library_service import import_seed
from ..resume_import import ImportDraft, parse_upload
from ..resume_import_commit import commit_import
from ..phase2j_repository import (
    picker as phase2j_picker,
)
from ..phase2k_repository import items as phase2k_items, counts as phase2k_counts, tags as phase2k_tags, create_item as phase2k_create_item, replace_tags as phase2k_replace_tags, bulk as phase2k_bulk, usages as phase2k_usages, detail as phase2k_detail, update_parent as phase2k_update_parent
from ..api_common import MAX_IMPORT_BYTES, SEED, found, owner

router = APIRouter()


# Reorder routes come first: "/api/library/summaries/order" would otherwise match the
# "/api/library/summaries/{rid}" route and fail UUID validation.
@router.put("/api/library/historical/{kind}/order")
async def order_historical(
    kind: str,
    req: ReorderRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        ok = await reorder_items(c, u["id"], kind, req.ids)
        found(ok, "One or more records were not found")
        return {"updated": True}


@router.put("/api/library/{kind}/order")
async def order_library(
    kind: str,
    req: ReorderRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        ok = await reorder(c, u["id"], kind, req.ids)
        found(ok, "One or more records were not found")
        return {"updated": True}


@router.get("/api/library", response_model=LibraryResponse)
async def library(identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        return await fetch_library(c, u["id"])


@router.post("/api/library/import/preview", response_model=ImportDraft)
async def preview_import(
    file: UploadFile = File(...),
    identity: CurrentUser = Depends(resolve_current_user),
):
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "File is larger than 10 MB.")
    try:
        # pdfminer and python-docx are CPU-bound; keep them off the event loop.
        draft = await asyncio.to_thread(parse_upload, file.filename or "", data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    async with connection() as c:
        await owner(identity, c)
    return draft


@router.post("/api/library/import/commit")
async def commit_reviewed_import(
    draft: ImportDraft, identity: CurrentUser = Depends(resolve_current_user)
):
    try:
        async with connection() as c:
            user = await owner(identity, c)
            return await commit_import(c, user["id"], draft, user["display_name"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/library/profiles", status_code=201)
async def add_profile(
    req: ProfileWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await create_profile(c, u["id"], req)
        if error == "duplicate":
            raise HTTPException(409, "A profile with that name already exists")
        return row


@router.put("/api/library/profiles/{rid}")
async def edit_profile(
    rid: UUID, req: ProfileWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await update_profile(c, u["id"], rid, req)
        if error == "duplicate":
            raise HTTPException(409, "A profile with that name already exists")
        return found(row, "Profile not found")


@router.post("/api/library/profiles/{rid}/duplicate", status_code=201)
async def copy_profile(
    rid: UUID,
    req: ProfileDuplicate,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await duplicate_profile(c, u["id"], rid, req.label)
        if error == "duplicate":
            raise HTTPException(409, "A profile with that name already exists")
        return found(row, "Profile not found")


@router.post("/api/library/summaries", status_code=201)
async def add_summary(
    req: SummaryWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        return await create_summary(c, u["id"], req)


@router.put("/api/library/summaries/{rid}")
async def edit_summary(
    rid: UUID, req: SummaryWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_summary(c, u["id"], rid, req)
        return found(row, "Summary variant not found")


@router.post("/api/library/summaries/{rid}/duplicate", status_code=201)
async def copy_summary(
    rid: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await duplicate_summary(c, u["id"], rid)
        return found(row, "Summary variant not found")


@router.post("/api/library/education", status_code=201)
async def add_education(
    req: EducationWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        return await create_education(c, u["id"], req)


@router.put("/api/library/education/{rid}")
async def edit_education(
    rid: UUID,
    req: EducationWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_education(c, u["id"], rid, req)
        return found(row, "Education item not found")


@router.post("/api/library/interests", status_code=201)
async def add_interest(
    req: InterestWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        return await create_interest(c, u["id"], req)


@router.put("/api/library/interests/{rid}")
async def edit_interest(
    rid: UUID, req: InterestWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_interest(c, u["id"], rid, req)
        return found(row, "Interest not found")


@router.post("/api/library/tool-groups", status_code=201)
async def add_tool_group(
    req: ToolGroupWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        return await create_tool_group(c, u["id"], req)


@router.put("/api/library/tool-groups/{rid}")
async def edit_tool_group(
    rid: UUID,
    req: ToolGroupWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_tool_group(c, u["id"], rid, req)
        return found(row, "Tool group not found")


@router.post("/api/library/tools", status_code=201)
async def add_tool(
    req: ToolWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await create_tool(c, u["id"], req)
        return found(row, "Tool group not found")


@router.put("/api/library/tools/{rid}")
async def edit_tool(
    rid: UUID, req: ToolWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_tool(c, u["id"], rid, req)
        return found(row, "Tool or group not found")


@router.put("/api/library/tool-groups/{gid}/tools/order")
async def order_tools(
    gid: UUID,
    req: ReorderRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        ok = await reorder_tools(c, u["id"], gid, req.ids)
        found(ok, "One or more tools were not found")
        return {"updated": True}


@router.post("/api/library/tools/{rid}/move")
async def move_one_tool(
    rid: UUID,
    req: ToolMoveRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await move_tool(c, u["id"], rid, req.group_id)
        return found(row, "Tool or destination group not found")


@router.post("/api/library/tools/{rid}/restore-explicit")
async def restore_one_tool(
    rid: UUID,
    req: ToolRestoreRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await restore_tool(c, u["id"], rid, req.outcome, req.group_id)
        if error == "parent":
            raise HTTPException(
                409, "Restore the parent group or choose an active destination group"
            )
        return found(row, "Tool not found")


@router.post("/api/library/bullets", status_code=201)
async def add_bullet(
    req: BulletCreate, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await create_bullet(c, u["id"], req)
        return found(row, "Resource not found")


@router.put("/api/library/parents/{parent_id}/bullets/order")
async def order_bullets(
    parent_id: UUID,
    req: ReorderRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        ok = await reorder_bullets(c, u["id"], parent_id, req.ids)
        found(ok, "Resource not found")
        return {"updated": True}


@router.post("/api/library/bullets/{bullet_id}/move")
async def move_one_bullet(
    bullet_id: UUID,
    req: BulletMove,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await move_bullet(c, u["id"], bullet_id, req.parent_id)
        return found(row, "Resource not found")


@router.post("/api/library/bullets/{bullet_id}/duplicate", status_code=201)
async def copy_bullet(
    bullet_id: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await duplicate_bullet(c, u["id"], bullet_id)
        return found(row, "Resource not found")


@router.post("/api/library/bullets/{bullet_id}/archive")
async def archive_one_bullet(
    bullet_id: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await archive_bullet(c, u["id"], bullet_id)
        return found(row, "Resource not found")


@router.post("/api/library/bullets/{bullet_id}/restore")
async def restore_one_bullet(
    bullet_id: UUID,
    req: BulletRestore,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await restore_bullet(c, u["id"], bullet_id, req.parent_id)
        if error == "parent":
            raise HTTPException(
                409, "Restore the parent or choose an active destination parent"
            )
        return found(row, "Resource not found")


@router.post("/api/library/bullets/{bullet_id}/variants", status_code=201)
async def add_variant(
    bullet_id: UUID,
    req: VariantWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await create_variant(c, u["id"], bullet_id, req)
        return found(row, "Resource not found")


@router.put("/api/library/variants/{variant_id}")
async def edit_variant(
    variant_id: UUID,
    req: VariantWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_variant(c, u["id"], variant_id, req)
        return found(row, "Resource not found")


@router.put("/api/library/bullets/{bullet_id}/variants/order")
async def order_variants(
    bullet_id: UUID,
    req: ReorderRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        ok = await reorder_variants(c, u["id"], bullet_id, req.ids)
        found(ok, "Resource not found")
        return {"updated": True}


@router.post("/api/library/variants/{variant_id}/duplicate", status_code=201)
async def copy_variant(
    variant_id: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await duplicate_variant(c, u["id"], variant_id)
        return found(row, "Resource not found")


@router.post("/api/library/variants/{variant_id}/default")
async def default_variant(
    variant_id: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await set_default_variant(c, u["id"], variant_id)
        return found(row, "Resource not found")


@router.post("/api/library/variants/{variant_id}/archive")
async def archive_one_variant(
    variant_id: UUID,
    req: VariantArchive,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await archive_variant(
            c, u["id"], variant_id, req.replacement_variant_id
        )
        if error == "last-active":
            raise HTTPException(409, "At least one active variant must remain")
        if error == "replacement":
            raise HTTPException(
                409,
                "Choose an active replacement default before archiving this variant",
            )
        return found(row, "Resource not found")


@router.post("/api/library/variants/{variant_id}/restore")
async def restore_one_variant(
    variant_id: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await restore_variant(c, u["id"], variant_id)
        return found(row, "Resource not found")


@router.post("/api/library/custom-sections", status_code=201)
async def add_custom_section(
    req: CustomSectionWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        return await create_custom_section(c, u["id"], req)


@router.put("/api/library/custom-sections/{rid}")
async def edit_custom_section(
    rid: UUID,
    req: CustomSectionWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_custom_section(c, u["id"], rid, req)
        return found(row, "Resource not found")


@router.post("/api/library/custom-entries", status_code=201)
async def add_custom_entry(
    req: CustomEntryWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await create_custom_entry(c, u["id"], req)
        return found(row, "Resource not found")


@router.put("/api/library/custom-entries/{rid}")
async def edit_custom_entry(
    rid: UUID,
    req: CustomEntryWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_custom_entry(c, u["id"], rid, req)
        return found(row, "Resource not found")


@router.put("/api/library/custom-sections/{sid}/entries/order")
async def order_custom_entries(
    sid: UUID,
    req: ReorderRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        ok = await reorder_custom_entries(c, u["id"], sid, req.ids)
        found(ok, "Resource not found")
        return {"updated": True}


@router.post("/api/library/custom-{kind}/{rid}/{action}")
async def archive_custom(
    kind: str,
    rid: UUID,
    action: str,
    identity: CurrentUser = Depends(resolve_current_user),
):
    if kind not in {"sections", "entries"} or action not in {"archive", "restore"}:
        raise HTTPException(404, "Resource not found")
    async with connection() as c:
        u = await owner(identity, c)
        row = await set_custom_archive(c, u["id"], kind, rid, action == "archive")
        return found(row, "Resource not found")


@router.get("/api/library/search")
async def library_search(
    q: str = "",
    status: str = Query("active", pattern="^(active|archived|all)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        return await search(c, u["id"], q, status, limit, offset)


@router.post("/api/library/{table}/{rid}/archive")
async def archive(
    table: str, rid: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await set_archive(c, u["id"], table, rid, True)
        return found(row, "Resource not found")


@router.post("/api/library/{table}/{rid}/restore")
async def restore(
    table: str, rid: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    if table in {"tools", "bullets", "bullet_variants"}:
        raise HTTPException(
            409, "Use the explicit tool restore endpoint to resolve the parent group"
        )
    async with connection() as c:
        u = await owner(identity, c)
        row = await set_archive(c, u["id"], table, rid, False)
        return found(row, "Resource not found")


@router.post("/api/library/import-seed", response_model=SeedImportResponse)
async def bootstrap(
    req: SeedImportRequest, identity: CurrentUser = Depends(resolve_current_user)
):
    try:
        async with connection() as c:
            u = await owner(identity, c)
            x, cid = await import_seed(c, u["id"], SEED, req.seed_key)
            return {"imported": x, "composition_id": cid}
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/api/library/items", status_code=201)
async def create_item(
    req: HistoricalItemWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        return {"id": await add_item(c, u["id"], req)}


@router.put("/api/library/items/{item_id}")
async def edit_item(
    item_id: UUID,
    req: HistoricalItemWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        updated = await update_item(c, u["id"], item_id, req)
        return {"id": found(updated, "Historical item not found")}


@router.post("/api/library/variants/{variant_id}/detach")
async def detach_bullet_variant(variant_id: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row = await detach_variant(c, u["id"], variant_id)
        if not row:
            raise HTTPException(404, "Variant not found")
        return row


@router.post("/api/library/bullets/{bullet_id}/attach")
async def attach_bullet_variant(bullet_id: UUID, req: AttachBulletWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await attach_bullet(c, u["id"], bullet_id, req.target_bullet_id)
        if error == "same":
            raise HTTPException(409, "Choose a different bullet")
        if not row:
            raise HTTPException(404, "Bullet not found")
        return row


@router.get("/api/library/bullet-picker")
async def bullet_picker(q: str = "", section: str = "", limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        return await phase2j_picker(c, u["id"], q, section, limit, offset)


@router.get("/api/library-management/items")
async def library_management_items(q: str="", status: str=Query("active",pattern="^(active|archived|all)$"), section: str="", tag_id: list[UUID]=Query(default=[]), page: int=Query(1,ge=1), page_size: int=Query(25,ge=1,le=100), identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); return await phase2k_items(c,u["id"],q,status,section,tag_id,page,page_size)


@router.get("/api/library-management/counts")
async def library_management_counts(identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); return await phase2k_counts(c,u["id"])


@router.get("/api/library-management/tags")
async def library_management_tags(q: str="", identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); return await phase2k_tags(c,u["id"],q)


@router.post("/api/library-management/items",status_code=201)
async def library_management_create(req: LibraryItemCreate, identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); return await phase2k_create_item(c,u["id"],req)


@router.put("/api/library-management/items/{bullet_id}/tags")
async def library_management_set_tags(bullet_id: UUID, req: LibraryTagsWrite, identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row=await phase2k_replace_tags(c,u["id"],bullet_id,req.names); return found(row, "Library item not found")


@router.post("/api/library-management/bulk")
async def library_management_bulk(req: LibraryBulkWrite, identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row=await phase2k_bulk(c,u["id"],req.ids,req.action,req.tag_names,req.section); return found(row, "One or more Library items were not found")


@router.get("/api/library-management/items/{bullet_id}")
async def library_management_detail(bullet_id: UUID, identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row=await phase2k_detail(c,u["id"],bullet_id); return found(row, "Library item not found")


@router.put("/api/library-management/items/{bullet_id}/parent")
async def library_management_parent(bullet_id: UUID, req: LibraryParentWrite, identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await phase2k_update_parent(c,u["id"],bullet_id,req.parent_id,req.parent_type)
        if error=="invalid": raise HTTPException(422,"Parent is not compatible with this Library section")
        return found(row, "Library item or parent not found")


@router.get("/api/library-management/items/{bullet_id}/usage")
async def library_management_usage(bullet_id: UUID, identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); return await phase2k_usages(c,u["id"],bullet_id)
