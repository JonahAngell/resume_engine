




import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from .database import (
    close_database,
    connection,
    database_health,
    migrate,
    open_database,
)
# Relationship resources retained for Phase 2C contract: 'bullets','bullet_variants'
from .editing_repository import (
    add_item,
    archive_bullet,
    archive_variant,
    create_bullet,
    create_composition,
    create_variant,
    duplicate,
    duplicate_bullet,
    duplicate_variant,
    get_revision,
    list_revisions,
    move_bullet,
    reorder_bullets,
    reorder_items,
    reorder_variants,
    restore_bullet,
    restore_revision,
    restore_variant,
    save_composition,
    select_historical,
    set_default_variant,
    update_item,
    update_variant,
    update_composition_metadata,
    set_composition_archive,
)
from .editing_schemas import (
    BulletCreate,
    BulletMove,
    BulletRestore,
    CompositionCreate,
    CompositionItemSelection,
    CompositionSave,
    CompositionState,
    DuplicateComposition,
    HistoricalItemWrite,
    RestoreRevision,
    VariantArchive,
    VariantWrite,
    CompositionMetadataWrite,
    CompositionLifecycleWrite,
    BulletPlacementWrite, BulletCreateAndPlace, BulletPlacementReplace,
    BulletPlacementReorder, BulletUsageUpdate, CompositionPreferencesWrite,
    EntryCreateWrite,
)
from .identity import CurrentUser, resolve_current_user
from .library_repository import (
    create_education,
    create_interest,
    create_summary,
    duplicate_summary,
    ensure_user,
    fetch_library,
    load_composition,
    reorder,
    save_profile,
    search,
    select_interest,
    select_summary,
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
    select_tool_group,
    create_custom_section,
    update_custom_section,
    create_custom_entry,
    update_custom_entry,
    reorder_custom_entries,
    set_custom_archive,
    save_sections_panel,
    reorder_composition_items,
    select_education,
    composition_items,
    create_and_include_entry,
)
from .library_schemas import (
    CompositionInterestSelection,
    CompositionSummarySelection,
    CurrentUserResponse,
    EducationWrite,
    InterestWrite,
    LibraryResponse,
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
    CompositionSectionsWrite,
    CompositionItemOrderWrite,
    LibraryItemCreate, LibraryTagsWrite, LibraryBulkWrite, LibraryParentWrite,
)
from .library_service import import_seed
from .phase2j_repository import (
    picker as phase2j_picker,
    insert_placement,
    create_and_place,
    remove_placement,
    replace_placement,
    reorder_placements,
    update_usage,
    usage_rows,
)
from .phase2k_repository import items as phase2k_items, counts as phase2k_counts, tags as phase2k_tags, create_item as phase2k_create_item, replace_tags as phase2k_replace_tags, bulk as phase2k_bulk, usages as phase2k_usages, detail as phase2k_detail, update_parent as phase2k_update_parent
from .phase2l_repository import update_preferences
from .phase2m_repository import materialize_composition, materialize_revision
from .render import render_resume
from .schemas import Resume

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seed" / "jonah-resume.json"
FRONTEND = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app):
    await open_database()
    await migrate()
    yield
    await close_database()


app = FastAPI(title="Resume Engine Phase 2", version="0.5.0", lifespan=lifespan)


async def owner(identity, conn):
    return await ensure_user(conn, identity)


def state(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row.get("description", ""),
        "display_title": row.get("display_title", ""),
        "target_company": row.get("target_company", ""),
        "target_role": row.get("target_role", ""),
        "preferred_page_length": row.get("preferred_page_length", 1),
        "date_format": row.get("date_format", "long"),
        "section_sort_modes": row.get("section_sort_modes", {}),
        "summary_variant_id": row.get("summary_variant_id"),
        "revision": row["revision"],
        "archived_at": row.get("archived_at"),
        "resume": Resume.model_validate(row["render_payload"]),
    }


@app.get("/health")
async def health():
    if not await database_health():
        raise HTTPException(503, "Database unavailable")
    return {"status": "ok", "database": "ok"}


@app.get("/api/seed", response_model=Resume)
def seed(identity: CurrentUser = Depends(resolve_current_user)):
    return Resume.model_validate_json(SEED.read_text())


@app.get("/api/me", response_model=CurrentUserResponse)
async def me(identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        return await owner(identity, c)


@app.get("/api/library", response_model=LibraryResponse)
async def library(identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        return await fetch_library(c, u["id"])


@app.put("/api/profile")
async def profile(
    req: ProfileWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        return await save_profile(c, u["id"], req)


@app.post("/api/library/summaries", status_code=201)
async def add_summary(
    req: SummaryWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        return await create_summary(c, u["id"], req)


@app.put("/api/library/summaries/{rid}")
async def edit_summary(
    rid: UUID, req: SummaryWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_summary(c, u["id"], rid, req)
        return row or (_ for _ in ()).throw(
            HTTPException(404, "Summary variant not found")
        )


@app.post("/api/library/summaries/{rid}/duplicate", status_code=201)
async def copy_summary(
    rid: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await duplicate_summary(c, u["id"], rid)
        return row or (_ for _ in ()).throw(
            HTTPException(404, "Summary variant not found")
        )


@app.post("/api/library/education", status_code=201)
async def add_education(
    req: EducationWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        return await create_education(c, u["id"], req)


@app.put("/api/library/education/{rid}")
async def edit_education(
    rid: UUID,
    req: EducationWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_education(c, u["id"], rid, req)
        return row or (_ for _ in ()).throw(
            HTTPException(404, "Education item not found")
        )


@app.post("/api/library/interests", status_code=201)
async def add_interest(
    req: InterestWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        return await create_interest(c, u["id"], req)


@app.put("/api/library/interests/{rid}")
async def edit_interest(
    rid: UUID, req: InterestWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_interest(c, u["id"], rid, req)
        return row or (_ for _ in ()).throw(HTTPException(404, "Interest not found"))


@app.put("/api/library/historical/{kind}/order")
async def order_historical(
    kind: str,
    req: ReorderRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        ok = await reorder_items(c, u["id"], kind, req.ids)
        return (
            {"updated": True}
            if ok
            else (_ for _ in ()).throw(
                HTTPException(404, "One or more records were not found")
            )
        )


@app.put("/api/library/{kind}/order")
async def order_library(
    kind: str,
    req: ReorderRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        ok = await reorder(c, u["id"], kind, req.ids)
        return (
            {"updated": True}
            if ok
            else (_ for _ in ()).throw(
                HTTPException(404, "One or more records were not found")
            )
        )


@app.post("/api/library/tool-groups", status_code=201)
async def add_tool_group(
    req: ToolGroupWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        return await create_tool_group(c, u["id"], req)


@app.put("/api/library/tool-groups/{rid}")
async def edit_tool_group(
    rid: UUID,
    req: ToolGroupWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_tool_group(c, u["id"], rid, req)
        return row or (_ for _ in ()).throw(HTTPException(404, "Tool group not found"))


@app.post("/api/library/tools", status_code=201)
async def add_tool(
    req: ToolWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await create_tool(c, u["id"], req)
        return row or (_ for _ in ()).throw(HTTPException(404, "Tool group not found"))


@app.put("/api/library/tools/{rid}")
async def edit_tool(
    rid: UUID, req: ToolWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_tool(c, u["id"], rid, req)
        return row or (_ for _ in ()).throw(
            HTTPException(404, "Tool or group not found")
        )


@app.put("/api/library/tool-groups/{gid}/tools/order")
async def order_tools(
    gid: UUID,
    req: ReorderRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        ok = await reorder_tools(c, u["id"], gid, req.ids)
        return (
            {"updated": True}
            if ok
            else (_ for _ in ()).throw(
                HTTPException(404, "One or more tools were not found")
            )
        )


@app.post("/api/library/tools/{rid}/move")
async def move_one_tool(
    rid: UUID,
    req: ToolMoveRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await move_tool(c, u["id"], rid, req.group_id)
        return row or (_ for _ in ()).throw(
            HTTPException(404, "Tool or destination group not found")
        )


@app.post("/api/library/tools/{rid}/restore-explicit")
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
        return row or (_ for _ in ()).throw(HTTPException(404, "Tool not found"))


@app.put("/api/compositions/{cid}/education", response_model=CompositionState)
async def choose_education(cid: UUID, req: CompositionItemSelection, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c);row,error=await select_education(c,u["id"],cid,req.revision,req.item_id,req.included)
        if error=="missing": raise HTTPException(404,"Composition or education item not found")
        if error=="stale": raise HTTPException(409,"Composition changed; reload before saving")
        return state(row)

@app.put("/api/compositions/{cid}/tool-groups", response_model=CompositionState)
async def choose_tool_group(
    cid: UUID,
    req: CompositionItemSelection,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await select_tool_group(
            c, u["id"], cid, req.revision, req.item_id, req.included
        )
        if error == "missing":
            raise HTTPException(404, "Composition or tool group not found")
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        return state(row)


@app.put(
    "/api/compositions/{cid}/historical/{section}", response_model=CompositionState
)
async def choose_historical(
    cid: UUID,
    section: str,
    req: CompositionItemSelection,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await select_historical(
            c, u["id"], cid, req.revision, section, req.item_id, req.included
        )
        if error == "missing":
            raise HTTPException(404, "Composition or historical item not found")
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        return state(row)


@app.post("/api/library/bullets", status_code=201)
async def add_bullet(
    req: BulletCreate, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await create_bullet(c, u["id"], req)
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.put("/api/library/parents/{parent_id}/bullets/order")
async def order_bullets(
    parent_id: UUID,
    req: ReorderRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        ok = await reorder_bullets(c, u["id"], parent_id, req.ids)
        return (
            {"updated": True}
            if ok
            else (_ for _ in ()).throw(HTTPException(404, "Resource not found"))
        )


@app.post("/api/library/bullets/{bullet_id}/move")
async def move_one_bullet(
    bullet_id: UUID,
    req: BulletMove,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await move_bullet(c, u["id"], bullet_id, req.parent_id)
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.post("/api/library/bullets/{bullet_id}/duplicate", status_code=201)
async def copy_bullet(
    bullet_id: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await duplicate_bullet(c, u["id"], bullet_id)
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.post("/api/library/bullets/{bullet_id}/archive")
async def archive_one_bullet(
    bullet_id: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await archive_bullet(c, u["id"], bullet_id)
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.post("/api/library/bullets/{bullet_id}/restore")
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
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.post("/api/library/bullets/{bullet_id}/variants", status_code=201)
async def add_variant(
    bullet_id: UUID,
    req: VariantWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await create_variant(c, u["id"], bullet_id, req)
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.put("/api/library/variants/{variant_id}")
async def edit_variant(
    variant_id: UUID,
    req: VariantWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_variant(c, u["id"], variant_id, req)
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.put("/api/library/bullets/{bullet_id}/variants/order")
async def order_variants(
    bullet_id: UUID,
    req: ReorderRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        ok = await reorder_variants(c, u["id"], bullet_id, req.ids)
        return (
            {"updated": True}
            if ok
            else (_ for _ in ()).throw(HTTPException(404, "Resource not found"))
        )


@app.post("/api/library/variants/{variant_id}/duplicate", status_code=201)
async def copy_variant(
    variant_id: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await duplicate_variant(c, u["id"], variant_id)
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.post("/api/library/variants/{variant_id}/default")
async def default_variant(
    variant_id: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await set_default_variant(c, u["id"], variant_id)
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.post("/api/library/variants/{variant_id}/archive")
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
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.post("/api/library/variants/{variant_id}/restore")
async def restore_one_variant(
    variant_id: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await restore_variant(c, u["id"], variant_id)
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.post("/api/library/custom-sections", status_code=201)
async def add_custom_section(
    req: CustomSectionWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        return await create_custom_section(c, u["id"], req)


@app.put("/api/library/custom-sections/{rid}")
async def edit_custom_section(
    rid: UUID,
    req: CustomSectionWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_custom_section(c, u["id"], rid, req)
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.post("/api/library/custom-entries", status_code=201)
async def add_custom_entry(
    req: CustomEntryWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await create_custom_entry(c, u["id"], req)
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.put("/api/library/custom-entries/{rid}")
async def edit_custom_entry(
    rid: UUID,
    req: CustomEntryWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await update_custom_entry(c, u["id"], rid, req)
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.put("/api/library/custom-sections/{sid}/entries/order")
async def order_custom_entries(
    sid: UUID,
    req: ReorderRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        ok = await reorder_custom_entries(c, u["id"], sid, req.ids)
        return (
            {"updated": True}
            if ok
            else (_ for _ in ()).throw(HTTPException(404, "Resource not found"))
        )


@app.post("/api/library/custom-{kind}/{rid}/{action}")
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
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.put("/api/compositions/{cid}/sections", response_model=CompositionState)
async def sections_panel(
    cid: UUID,
    req: CompositionSectionsWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await save_sections_panel(c, u["id"], cid, req)
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        if error == "invalid":
            raise HTTPException(422, "Invalid section order or inclusion state")
        if error == "missing":
            raise HTTPException(404, "Resource not found")
        return state(row)


@app.get("/api/compositions/{cid}/items")
async def get_composition_items(cid: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); rows=await composition_items(c,u["id"],cid)
        if rows is None: raise HTTPException(404,"Composition not found")
        return rows
@app.post("/api/compositions/{cid}/entries/create", response_model=CompositionState, status_code=201)
async def create_composition_entry(cid: UUID, req: EntryCreateWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await create_and_include_entry(c,u["id"],cid,req)
        if error=="missing": raise HTTPException(404,"Resource not found")
        if error=="stale": raise HTTPException(409,"Composition changed; reload before saving")
        if error=="invalid": raise HTTPException(422,"Unsupported entry section")
        return state(row)
@app.put("/api/compositions/{cid}/items/order", response_model=CompositionState)
async def order_composition_items(cid: UUID, req: CompositionItemOrderWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await reorder_composition_items(c, u["id"], cid, req)
        if error == "stale": raise HTTPException(409, "Composition changed; reload before saving")
        if error == "missing": raise HTTPException(404, "Resource not found")
        if error == "invalid": raise HTTPException(422, "Invalid selected-item order")
        return state(row)

@app.get("/api/library/search")
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


@app.post("/api/library/{table}/{rid}/archive")
async def archive(
    table: str, rid: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await set_archive(c, u["id"], table, rid, True)
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.post("/api/library/{table}/{rid}/restore")
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
        return row or (_ for _ in ()).throw(HTTPException(404, "Resource not found"))


@app.post("/api/library/import-seed", response_model=SeedImportResponse)
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


@app.post("/api/library/items", status_code=201)
async def create_item(
    req: HistoricalItemWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        return {"id": await add_item(c, u["id"], req)}


@app.put("/api/library/items/{item_id}")
async def edit_item(
    item_id: UUID,
    req: HistoricalItemWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        found = await update_item(c, u["id"], item_id, req)
        return (
            {"id": found}
            if found
            else (_ for _ in ()).throw(HTTPException(404, "Historical item not found"))
        )


@app.post("/api/compositions", response_model=CompositionState, status_code=201)
async def new_comp(
    req: CompositionCreate, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        resume = Resume(header={"name": u["display_name"]})
        row = await create_composition(
            c,
            u["id"],
            req.name,
            req.description,
            resume,
            display_name=u["display_name"],
            display_title=req.display_title,
            target_company=req.target_company,
            target_role=req.target_role,
        )
        return state(row)


@app.get("/api/compositions/{cid}", response_model=CompositionState)
async def get_comp(cid: UUID, include_archived: bool = False, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row = await load_composition(c, u["id"], cid, include_archived)
        return (
            state(row)
            if row
            else (_ for _ in ()).throw(HTTPException(404, "Composition not found"))
        )


@app.put("/api/compositions/{cid}/metadata", response_model=CompositionState)
async def edit_composition_metadata(cid: UUID, req: CompositionMetadataWrite, identity: CurrentUser = Depends(resolve_current_user)):
    try:
        async with connection() as c:
            u=await owner(identity,c);row,error=await update_composition_metadata(
                c,u["id"],cid,req.revision,req.name,req.description,
                req.display_title,req.target_company,req.target_role
            )
            if error=="missing": raise HTTPException(404,"Composition not found")
            if error=="stale": raise HTTPException(409,"Composition changed; reload before saving")
            return state(row)
    except HTTPException: raise
    except Exception as e:
        if "unique" in str(e).lower(): raise HTTPException(409,"A composition with that name already exists")
        raise
@app.post("/api/compositions/{cid}/archive", response_model=CompositionState)
async def archive_composition(cid: UUID, req: CompositionLifecycleWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c);row,error=await set_composition_archive(c,u["id"],cid,req.revision,True)
        if error=="missing": raise HTTPException(404,"Composition not found")
        if error=="stale": raise HTTPException(409,"Composition changed; reload before saving")
        return state(row)
@app.post("/api/compositions/{cid}/restore", response_model=CompositionState)
async def restore_composition(cid: UUID, req: CompositionLifecycleWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c);row,error=await set_composition_archive(c,u["id"],cid,req.revision,False)
        if error=="missing": raise HTTPException(404,"Composition not found")
        if error=="stale": raise HTTPException(409,"Composition changed; reload before saving")
        return state(row)
@app.put("/api/compositions/{cid}", response_model=CompositionState)
async def autosave(
    cid: UUID,
    req: CompositionSave,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await save_composition(
            c, u["id"], cid, req.revision, req.resume.model_dump(), req.source
        )
        if not row:
            if not await load_composition(c, u["id"], cid):
                raise HTTPException(404, "Composition not found")
            raise HTTPException(409, "Composition changed; reload before saving")
        return state(row)



@app.put("/api/compositions/{cid}/preferences", response_model=CompositionState)
async def composition_preferences(cid: UUID, req: CompositionPreferencesWrite, identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await update_preferences(c,u["id"],cid,req)
        if error=="missing": raise HTTPException(404,"Composition not found")
        if error=="stale": raise HTTPException(409,"Composition changed; reload before saving")
        return state(row)

@app.put("/api/compositions/{cid}/summary", response_model=CompositionState)
async def choose_summary(
    cid: UUID,
    req: CompositionSummarySelection,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await select_summary(
            c, u["id"], cid, req.revision, req.summary_variant_id
        )
        if error == "missing":
            raise HTTPException(404, "Composition or summary variant not found")
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        return state(row)


@app.put("/api/compositions/{cid}/interests", response_model=CompositionState)
async def choose_interest(
    cid: UUID,
    req: CompositionInterestSelection,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await select_interest(
            c, u["id"], cid, req.revision, req.interest_id, req.included
        )
        if error == "missing":
            raise HTTPException(404, "Composition or interest not found")
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        return state(row)


@app.post(
    "/api/compositions/{cid}/duplicate",
    response_model=CompositionState,
    status_code=201,
)
async def copy_comp(
    cid: UUID,
    req: DuplicateComposition,
    identity: CurrentUser = Depends(resolve_current_user),
):
    try:
        async with connection() as c:
            u = await owner(identity, c)
            row = await duplicate(c, u["id"], cid, req.name)
            return (
                state(row)
                if row
                else (_ for _ in ()).throw(HTTPException(404, "Composition not found"))
            )
    except HTTPException:
        raise
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(409, "A composition with that name already exists")
        raise


@app.get("/api/compositions/{cid}/revisions")
async def revisions(cid: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        return await list_revisions(c, u["id"], cid)


@app.get("/api/compositions/{cid}/revisions/{rid}")
async def revision(
    cid: UUID, rid: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await get_revision(c, u["id"], cid, rid)
        return row or (_ for _ in ()).throw(HTTPException(404, "Revision not found"))


@app.post(
    "/api/compositions/{cid}/revisions/{rid}/restore", response_model=CompositionState
)
async def restore_rev(
    cid: UUID,
    rid: UUID,
    req: RestoreRevision,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await restore_revision(c, u["id"], cid, rid, req.revision)
        if error == "missing":
            raise HTTPException(404, "Revision not found")
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before restoring")
        if error == "name-conflict":
            old=await get_revision(c,u["id"],cid,rid); name=(old or {}).get("snapshot",{}).get("name","")
            raise HTTPException(409,f"Another resume already uses the name '{name}'. Rename it or restore a different revision.")
        return state(row)



@app.get("/api/compositions/{cid}/revisions/{rid}/render",response_class=HTMLResponse)
async def render_revision(cid:UUID,rid:UUID,identity:CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c);materialized,error=await materialize_revision(c,u["id"],cid,rid)
        if error:raise HTTPException(404,"Revision not found")
        return HTMLResponse(render_resume(materialized["resume"],True,materialized["renderer_contract_version"],materialized["section_sort_modes"],materialized["date_format"]))

@app.get("/api/library/bullet-picker")
async def bullet_picker(q: str = "", section: str = "", limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        return await phase2j_picker(c, u["id"], q, section, limit, offset)

def _placement_result(row, error):
    if error == "missing": raise HTTPException(404, "Resource not found")
    if error == "stale": raise HTTPException(409, "Composition changed; reload before saving")
    if error == "invalid": raise HTTPException(422, "Invalid placement order")
    if error == "duplicate": raise HTTPException(409, "This bullet is already in this resume.")
    if error == "section": raise HTTPException(422, "This bullet belongs to a different section.")
    return state(row)

@app.get("/api/compositions/{cid}/bullet-placements")
async def bullet_placements(cid: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c)
        if not await load_composition(c,u["id"],cid): raise HTTPException(404,"Composition not found")
        return await usage_rows(c,u["id"],cid)

@app.post("/api/compositions/{cid}/bullet-placements", response_model=CompositionState)
async def add_bullet_placement(cid: UUID, req: BulletPlacementWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await insert_placement(c,u["id"],cid,req)
        return _placement_result(row,error)

@app.post("/api/compositions/{cid}/bullet-placements/create", response_model=CompositionState)
async def create_bullet_placement(cid: UUID, req: BulletCreateAndPlace, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await create_and_place(c,u["id"],cid,req)
        return _placement_result(row,error)

@app.put("/api/compositions/{cid}/bullet-placements/order", response_model=CompositionState)
async def order_bullet_placements(cid: UUID, req: BulletPlacementReorder, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await reorder_placements(c,u["id"],cid,req)
        return _placement_result(row,error)

@app.delete("/api/compositions/{cid}/bullet-placements/{placement_id}", response_model=CompositionState)
async def delete_bullet_placement(cid: UUID, placement_id: UUID, revision: int = Query(..., ge=1), identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await remove_placement(c,u["id"],cid,placement_id,revision)
        return _placement_result(row,error)

@app.put("/api/compositions/{cid}/bullet-placements/{placement_id}", response_model=CompositionState)
async def change_bullet_placement(cid: UUID, placement_id: UUID, req: BulletPlacementReplace, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await replace_placement(c,u["id"],cid,placement_id,req)
        return _placement_result(row,error)

@app.post("/api/compositions/{cid}/bullet-placements/{placement_id}/update-usage", response_model=CompositionState)
async def refresh_bullet_usage(cid: UUID, placement_id: UUID, req: BulletUsageUpdate, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await update_usage(c,u["id"],cid,placement_id,req.revision)
        return _placement_result(row,error)

@app.post("/api/render", response_class=HTMLResponse)
def render(payload: Resume, identity: CurrentUser = Depends(resolve_current_user)):
    # Compatibility-only preview. Secure export never accepts this payload.
    return HTMLResponse(render_resume(payload, True))

@app.get("/api/compositions/{cid}/render", response_class=HTMLResponse)
async def render_composition(cid: UUID, revision: int | None = None, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c)
        materialized,error=await materialize_composition(c,u["id"],cid,revision)
        if error=="stale": raise HTTPException(409,"Composition changed; reload before rendering")
        if error: raise HTTPException(404,"Composition not found")
        return HTMLResponse(render_resume(materialized["resume"],True,materialized["renderer_contract_version"],materialized.get("section_sort_modes",{}),materialized.get("date_format","long")))

def _pdf_page_count(content: bytes) -> int:
    import re
    return len(re.findall(rb"/Type\s*/Page\b", content))

def _safe_filename(value: str) -> str:
    import re
    value=re.sub(r"[^A-Za-z0-9._ -]+","",value).strip(" .")
    return (value or "resume")[:100]+".pdf"

@app.post("/api/compositions/{cid}/export/pdf")
async def export_composition_pdf(cid: UUID, revision: int | None = Query(default=None,ge=1), identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c)
        materialized,error=await materialize_composition(c,u["id"],cid,revision)
    if error=="stale": raise HTTPException(409,"Composition changed; save or reload before exporting")
    if error: raise HTTPException(404,"Composition not found")
    html=render_resume(materialized["resume"],False,materialized["renderer_contract_version"],materialized.get("section_sort_modes",{}),materialized.get("date_format","long"))
    url=os.getenv("GOTENBERG_URL","http://gotenberg:3000").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            rendered=await client.post(f"{url}/forms/chromium/convert/html",files={"files":("index.html",html.encode(),"text/html")},data={"paperWidth":"8.5","paperHeight":"11","preferCssPageSize":"true","printBackground":"true"})
            rendered.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502,"PDF renderer unavailable") from exc
    actual=_pdf_page_count(rendered.content)
    preferred=materialized["preferred_page_count"]
    if actual < 1: raise HTTPException(502,"PDF renderer returned an invalid document")
    if actual > preferred:
        raise HTTPException(409,f"Export blocked: resume uses {actual} pages; preferred length is {preferred}.")
    filename=_safe_filename(materialized["name"])
    return Response(rendered.content,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="{filename}"',"X-Resume-Page-Count":str(actual),"X-Renderer-Contract":materialized["renderer_contract_version"]})

@app.post("/api/export/pdf")
async def raw_export_disabled(payload: Resume, identity: CurrentUser = Depends(resolve_current_user)):
    raise HTTPException(410,"Raw-payload export is disabled. Export an owned composition instead.")
@app.get("/api/library-management/items")
async def library_management_items(q: str="", status: str=Query("active",pattern="^(active|archived|all)$"), section: str="", tag_id: list[UUID]=Query(default=[]), page: int=Query(1,ge=1), page_size: int=Query(25,ge=1,le=100), identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); return await phase2k_items(c,u["id"],q,status,section,tag_id,page,page_size)
@app.get("/api/library-management/counts")
async def library_management_counts(identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); return await phase2k_counts(c,u["id"])
@app.get("/api/library-management/tags")
async def library_management_tags(q: str="", identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); return await phase2k_tags(c,u["id"],q)
@app.post("/api/library-management/items",status_code=201)
async def library_management_create(req: LibraryItemCreate, identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); return await phase2k_create_item(c,u["id"],req)
@app.put("/api/library-management/items/{bullet_id}/tags")
async def library_management_set_tags(bullet_id: UUID, req: LibraryTagsWrite, identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row=await phase2k_replace_tags(c,u["id"],bullet_id,req.names); return row or (_ for _ in ()).throw(HTTPException(404,"Library item not found"))
@app.post("/api/library-management/bulk")
async def library_management_bulk(req: LibraryBulkWrite, identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row=await phase2k_bulk(c,u["id"],req.ids,req.action,req.tag_names,req.section); return row or (_ for _ in ()).throw(HTTPException(404,"One or more Library items were not found"))
@app.get("/api/library-management/items/{bullet_id}")
async def library_management_detail(bullet_id: UUID, identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row=await phase2k_detail(c,u["id"],bullet_id); return row or (_ for _ in ()).throw(HTTPException(404,"Library item not found"))
@app.put("/api/library-management/items/{bullet_id}/parent")
async def library_management_parent(bullet_id: UUID, req: LibraryParentWrite, identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await phase2k_update_parent(c,u["id"],bullet_id,req.parent_id,req.parent_type)
        if error=="invalid": raise HTTPException(422,"Parent is not compatible with this Library section")
        return row or (_ for _ in ()).throw(HTTPException(404,"Library item or parent not found"))
@app.get("/api/library-management/items/{bullet_id}/usage")
async def library_management_usage(bullet_id: UUID, identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); return await phase2k_usages(c,u["id"],bullet_id)

if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")





