




import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID
import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from urllib.parse import urlparse
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
    AiVariantAccept,
    AiVariantRequest,
    BulletPlacementReplaceMany,
    VariantPickRequest,
    CondenseApply,
    CondenseRequest,
    KeywordAssistRequest,
    KeywordBulletAccept,
    KeywordDefineRequest,
    AtsScoreRequest,
    SkillAddWrite,
    SkillRecommendRequest,
    BulletCreate,
    BulletMove,
    BulletRestore,
    CompositionCreate,
    CompositionItemSelection,
    ToolVisibilityWrite,
    ToolOrderWrite,
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
    BulletSaveChoice,
    EntrySaveChoice,
    SummarySaveChoice,
    ProfileSaveChoice,
    DefaultSetArchive,
    DefaultSetBulk,
    DefaultSetFromComposition,
    DefaultSetMembershipsWrite,
    DefaultSetWrite,
    AttachBulletWrite,
)
from .resume_variants import (
    attach_bullet,
    apply_library_selection,
    detach_variant,
    save_bullet_edit,
    save_entry_edit,
    save_profile_edit,
    save_summary_edit,
)
from . import default_sets
from .ai_recommend import recommend_resume
from .ai_client import close_shared_client, providers as ai_providers
from .identity import CurrentUser, check_local_auth_safety, resolve_current_user
from .library_repository import (
    add_skill_to_resume,
    load_skill_inputs,
    create_education,
    create_interest,
    create_profile,
    create_summary,
    duplicate_profile,
    duplicate_summary,
    ensure_user,
    fetch_library,
    load_composition,
    reorder,
    search,
    select_interest,
    select_profile,
    select_summary,
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
    select_tool_group,
    hidden_tools,
    set_tool_visibility,
    tool_order,
    set_tool_order,
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
    CompositionProfileSelection,
    CompositionSummarySelection,
    CurrentUserResponse,
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
    CompositionSectionsWrite,
    CompositionItemOrderWrite,
    LibraryItemCreate, LibraryTagsWrite, LibraryBulkWrite, LibraryParentWrite,
)
from .library_service import import_seed
from .resume_import import ImportDraft, parse_upload
from .resume_import_commit import commit_import
from .ai_review import review_resume
from .ai_schemas import AiReview, AtsScore, ChatRequest, ChatTurn, CoachResult, KeywordAssist, KeywordDefinition, ResumeRecommendRequest, ResumeRecommendResult, VariantPick, VariantSuggestions
from .ai_define import define_keyword
from .ai_variant_pick import pick_variants
from .ai_condense import condense_resume
from .ai_schemas import CondenseResult
from .ai_chat import chat_turn
from .ai_coach import coach_resume
from .ai_keyword import PLACEHOLDER, assist_keyword, new_bullet_key
from .ai_variants import issued_draft, job_tool_terms, suggest_variants
from .ats_score import score_resume
from .job_match import is_skill_keyword, match_qualifications
from .related_skills import category_for_term
from .skill_groups import recommend_group, recommend_with_ai
from .job_repository import (
    analyze_job_description,
    archive_job_description,
    compare_job_description,
    create_job_description,
    get_job_description,
    link_job_composition,
    list_job_descriptions,
    load_ai_review_inputs,
    load_chat_inputs,
    load_entry_section,
    load_pick_inputs,
    load_condense_inputs,
    load_variant_inputs,
    update_job_description,
)
from .job_schemas import (
    JobAnalysis,
    JobDescriptionRecord,
    JobDescriptionWrite,
    JobMatch,
    JobMatchRequest,
)
from .phase2j_repository import (
    picker as phase2j_picker,
    insert_placement,
    create_and_place,
    remove_placement,
    replace_placement,
    replace_placements,
    reorder_placements,
    apply_condense,
    update_usage,
    usage_rows,
)
from .phase2k_repository import items as phase2k_items, counts as phase2k_counts, tags as phase2k_tags, create_item as phase2k_create_item, replace_tags as phase2k_replace_tags, bulk as phase2k_bulk, usages as phase2k_usages, detail as phase2k_detail, update_parent as phase2k_update_parent
from .phase2l_repository import update_preferences
from .phase2m_repository import materialize_composition, materialize_revision
from .rate_limit import ai_rate_limit, limiter
from .render import render_resume
from .schemas import Resume

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seed" / "nia-calder-resume.json"
FRONTEND = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app):
    check_local_auth_safety()
    await open_database()
    await migrate()
    yield
    await close_shared_client()
    await close_database()


app = FastAPI(title="Resume Engine Phase 2", version="0.5.0", lifespan=lifespan)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
MAX_JSON_BYTES = 2 * 1024 * 1024
UPLOAD_PATH = "/api/library/import/preview"


@app.middleware("http")
async def request_guard(request, call_next):
    """Reject cross-site writes and oversized bodies before any handler runs."""
    if request.method not in SAFE_METHODS:
        site = request.headers.get("sec-fetch-site")
        origin = request.headers.get("origin")
        cross_site = False
        if site is not None:
            cross_site = site not in {"same-origin", "none"}
        elif origin is not None:
            cross_site = urlparse(origin).netloc != request.headers.get("host", "")
        if cross_site:
            return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
        limit = MAX_IMPORT_BYTES + 64 * 1024 if request.url.path == UPLOAD_PATH else MAX_JSON_BYTES
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > limit:
            return JSONResponse({"detail": "Request body is too large."}, status_code=413)
    return await call_next(request)


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
        "job_description_id": row.get("job_description_id"),
        "preferred_page_length": row.get("preferred_page_length", 1),
        "date_format": row.get("date_format", "long"),
        "template_style": row.get("template_style", "classic"),
        "skill_row_max": row.get("skill_row_max", 4),
        "section_sort_modes": row.get("section_sort_modes", {}),
        "summary_variant_id": row.get("summary_variant_id"),
        "profile_id": row.get("profile_id"),
        "is_starter": row.get("is_starter", False),
        "is_default_starter": row.get("is_default_starter", False),
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


@app.get("/api/ai/status")
def ai_status(identity: CurrentUser = Depends(resolve_current_user)):
    chain = ai_providers()
    return {
        "available": bool(chain),
        "providers": [{"name": p.name, "models": list(p.models)} for p in chain],
    }


@app.get("/api/library", response_model=LibraryResponse)
async def library(identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        return await fetch_library(c, u["id"])


MAX_IMPORT_BYTES = 10 * 1024 * 1024


@app.post("/api/library/import/preview", response_model=ImportDraft)
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


@app.post("/api/library/import/commit")
async def commit_reviewed_import(
    draft: ImportDraft, identity: CurrentUser = Depends(resolve_current_user)
):
    try:
        async with connection() as c:
            user = await owner(identity, c)
            return await commit_import(c, user["id"], draft, user["display_name"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/library/profiles", status_code=201)
async def add_profile(
    req: ProfileWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await create_profile(c, u["id"], req)
        if error == "duplicate":
            raise HTTPException(409, "A profile with that name already exists")
        return row


@app.put("/api/library/profiles/{rid}")
async def edit_profile(
    rid: UUID, req: ProfileWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await update_profile(c, u["id"], rid, req)
        if error == "duplicate":
            raise HTTPException(409, "A profile with that name already exists")
        return row or (_ for _ in ()).throw(HTTPException(404, "Profile not found"))


@app.post("/api/library/profiles/{rid}/duplicate", status_code=201)
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
        return row or (_ for _ in ()).throw(HTTPException(404, "Profile not found"))


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


@app.get("/api/compositions/{cid}/tool-order")
async def composition_tool_order(
    cid: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        rows = await tool_order(c, u["id"], cid)
        if rows is None:
            raise HTTPException(404, "Composition not found")
        return [
            {"tool_id": str(row["tool_id"]), "sort_order": row["sort_order"]}
            for row in rows
        ]


@app.put(
    "/api/compositions/{cid}/tool-groups/{group_id}/tools/order",
    response_model=CompositionState,
)
async def order_composition_tools(
    cid: UUID,
    group_id: UUID,
    req: ToolOrderWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await set_tool_order(
            c, u["id"], cid, req.revision, group_id, req.ids
        )
        if error == "missing":
            raise HTTPException(404, "Composition or skill group not found")
        if error == "invalid":
            raise HTTPException(400, "Skill order must include every skill in the group")
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        return state(row)


@app.get("/api/compositions/{cid}/hidden-tools")
async def composition_hidden_tools(
    cid: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        rows = await hidden_tools(c, u["id"], cid)
        if rows is None:
            raise HTTPException(404, "Composition not found")
        return [{"tool_id": str(row["tool_id"])} for row in rows]


@app.put("/api/compositions/{cid}/tools/{tool_id}", response_model=CompositionState)
async def choose_tool_visibility(
    cid: UUID,
    tool_id: UUID,
    req: ToolVisibilityWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await set_tool_visibility(
            c, u["id"], cid, req.revision, tool_id, req.included
        )
        if error == "missing":
            raise HTTPException(404, "Composition or skill not found")
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        return state(row)


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


@app.post("/api/compositions/{cid}/skills/recommend")
async def recommend_skill_group(cid: UUID, req: SkillRecommendRequest, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        inputs = await load_skill_inputs(c, u["id"], cid)
    if inputs is None:
        raise HTTPException(404, "Composition not found")
    # Local data first; the model only runs on a second call when that found nothing.
    if req.allow_ai:
        limiter.check(identity.external_id)
        return await recommend_with_ai(req.keyword, inputs["groups"], inputs["tools"])
    return recommend_group(req.keyword, inputs["groups"], inputs["tools"])


@app.post("/api/compositions/{cid}/skills", response_model=CompositionState)
async def add_skill(cid: UUID, req: SkillAddWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await add_skill_to_resume(
            c, u["id"], cid, req.revision, req.name, req.group_id, req.new_group_name
        )
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        if error == "invalid":
            raise HTTPException(422, "Name the skill and its group")
        if error or not row:
            raise HTTPException(404, "Composition or skill group not found")
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


async def build_resume(
    c,
    u,
    *,
    selection=None,
    source="library-defaults",
    job_description_id=None,
    name=None,
    description="",
    display_title="",
    target_company="",
    target_role="",
):
    """Create a resume, fill it from the library, and optionally link a job."""
    if job_description_id and not await get_job_description(c, u["id"], job_description_id):
        raise HTTPException(404, "Job description not found")
    resume = Resume(header={"name": u["display_name"]})
    row = await create_composition(
        c,
        u["id"],
        name,
        description,
        resume,
        display_name=u["display_name"],
        display_title=display_title,
        target_company=target_company,
        target_role=target_role,
    )
    row = await apply_library_selection(c, u["id"], row["id"], selection, source)
    if job_description_id:
        row, error = await update_composition_metadata(
            c,
            u["id"],
            row["id"],
            row["revision"],
            row["name"],
            row.get("description") or "",
            row.get("display_title") or "",
            job_description_id=job_description_id,
            link_job=True,
        )
        if error:
            raise HTTPException(404, "Job description not found")
    return row


@app.post("/api/compositions", response_model=CompositionState, status_code=201)
async def new_comp(
    req: CompositionCreate, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        set_id = req.default_set_id
        if set_id is None and not req.entire_library:
            found = await default_sets.default_set(c, u["id"])
            set_id = found["id"] if found else None
        selection = None
        if set_id:
            selection = await default_sets.load_selection(c, u["id"], set_id)
            if selection is None:
                raise HTTPException(404, "Defaults set not found")
        row = await build_resume(
            c,
            u,
            selection=selection,
            source="default-set" if selection else "library-defaults",
            job_description_id=req.job_description_id,
            name=req.name,
            description=req.description,
            display_title=req.display_title,
            target_company=req.target_company,
            target_role=req.target_role,
        )
        return state(row)


@app.post("/api/compositions/ai-recommend", response_model=ResumeRecommendResult, status_code=201, dependencies=[Depends(ai_rate_limit)])
async def ai_recommend_resume(
    req: ResumeRecommendRequest, identity: CurrentUser = Depends(resolve_current_user)
):
    """Build a new resume from the library records most relevant to one saved job."""
    async with connection() as c:
        u = await owner(identity, c)
        job = await get_job_description(c, u["id"], req.job_description_id)
        if not job:
            raise HTTPException(404, "Job description not found")
        library = await fetch_library(c, u["id"])
    # The model call can take a while; do not hold a pooled connection during it.
    result = await recommend_resume(job.get("body") or "", library)
    label = " – ".join(part for part in (job.get("role"), job.get("company")) if part)
    async with connection() as c:
        u = await owner(identity, c)
        row = await build_resume(
            c,
            u,
            selection=result.pop("selection"),
            source="ai-recommendation",
            job_description_id=req.job_description_id,
            name=req.name,
            display_title=job.get("role") or "",
        )
    return {**result, "composition": state(row)}


@app.get("/api/default-sets")
async def list_default_sets(identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        return {
            "sets": await default_sets.list_sets(c, u["id"], include_archived=True),
            "members": await default_sets.list_members(c, u["id"]),
        }


@app.post("/api/default-sets", status_code=201)
async def create_default_set(req: DefaultSetWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await default_sets.create_set(c, u["id"], req.name, req.description)
        if error == "name":
            raise HTTPException(409, "A defaults set with that name already exists")
        return row


@app.put("/api/default-sets/memberships")
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


@app.put("/api/default-sets/{set_id}")
async def update_default_set(set_id: UUID, req: DefaultSetWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await default_sets.update_set(c, u["id"], set_id, req.name, req.description)
        if error == "name":
            raise HTTPException(409, "A defaults set with that name already exists")
        return row or (_ for _ in ()).throw(HTTPException(404, "Defaults set not found"))


@app.post("/api/default-sets/{set_id}/archive")
async def archive_default_set(set_id: UUID, req: DefaultSetArchive, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await default_sets.archive_set(c, u["id"], set_id, req.archived)
        if error == "name":
            raise HTTPException(409, "An active defaults set already uses that name")
        return row or (_ for _ in ()).throw(HTTPException(404, "Defaults set not found"))


@app.post("/api/default-sets/{set_id}/default")
async def make_default_set(set_id: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row = await default_sets.set_default(c, u["id"], set_id)
        return row or (_ for _ in ()).throw(HTTPException(404, "Defaults set not found"))


@app.post("/api/default-sets/{set_id}/bulk")
async def bulk_default_set(set_id: UUID, req: DefaultSetBulk, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row = await default_sets.bulk_bullets(c, u["id"], set_id, req.action, req.bullet_ids)
        return row or (_ for _ in ()).throw(HTTPException(404, "Defaults set not found"))


@app.post("/api/compositions/{cid}/default-set", status_code=201)
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


@app.post("/api/compositions/{cid}/bullet-placements/{placement_id}/save", response_model=CompositionState)
async def save_bullet_choice(cid: UUID, placement_id: UUID, req: BulletSaveChoice, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await save_bullet_edit(c, u["id"], cid, placement_id, req.revision, req.body, req.mode)
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        if not row:
            raise HTTPException(404, "Bullet not found")
        return state(row)


@app.post("/api/compositions/{cid}/entries/{item_id}/save", response_model=CompositionState)
async def save_entry_choice(cid: UUID, item_id: UUID, req: EntrySaveChoice, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await save_entry_edit(c, u["id"], cid, item_id, req.revision, req.section, req.fields, req.mode)
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        if not row:
            raise HTTPException(404, "Entry not found")
        return state(row)


@app.post("/api/compositions/{cid}/summaries/{summary_id}/save", response_model=CompositionState)
async def save_summary_choice(cid: UUID, summary_id: UUID, req: SummarySaveChoice, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await save_summary_edit(c, u["id"], cid, summary_id, req.revision, req.name, req.body, req.mode)
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        if not row:
            raise HTTPException(404, "Summary not found")
        return state(row)


@app.post("/api/compositions/{cid}/profiles/{profile_id}/save", response_model=CompositionState)
async def save_profile_choice(cid: UUID, profile_id: UUID, req: ProfileSaveChoice, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await save_profile_edit(c, u["id"], cid, profile_id, req.revision, req.fields, req.mode)
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        if not row:
            raise HTTPException(404, "Profile not found")
        return state(row)


@app.post("/api/library/variants/{variant_id}/detach")
async def detach_bullet_variant(variant_id: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row = await detach_variant(c, u["id"], variant_id)
        if not row:
            raise HTTPException(404, "Variant not found")
        return row


@app.post("/api/library/bullets/{bullet_id}/attach")
async def attach_bullet_variant(bullet_id: UUID, req: AttachBulletWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await attach_bullet(c, u["id"], bullet_id, req.target_bullet_id)
        if error == "same":
            raise HTTPException(409, "Choose a different bullet")
        if not row:
            raise HTTPException(404, "Bullet not found")
        return row


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
                req.display_title,req.target_company,req.target_role,
                job_description_id=req.job_description_id,
                link_job="job_description_id" in req.model_fields_set,
            )
            if error=="missing": raise HTTPException(404,"Composition not found")
            if error=="job": raise HTTPException(404,"Job description not found")
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

@app.put("/api/compositions/{cid}/profile", response_model=CompositionState)
async def choose_profile(
    cid: UUID,
    req: CompositionProfileSelection,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await select_profile(
            c, u["id"], cid, req.revision, req.profile_id
        )
        if error == "missing":
            raise HTTPException(404, "Composition or profile not found")
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
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
        return HTMLResponse(render_resume(materialized["resume"],True,materialized["renderer_contract_version"],materialized["section_sort_modes"],materialized["date_format"],materialized.get("template_style","classic"),materialized.get("skill_row_max",4)))

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

@app.post("/api/compositions/{cid}/bullet-placements/replace-many", response_model=CompositionState)
async def change_bullet_placements(cid: UUID, req: BulletPlacementReplaceMany, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await replace_placements(c,u["id"],cid,req)
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

@app.post("/api/compositions/{cid}/bullet-placements/{placement_id}/ai-variants", response_model=VariantSuggestions, dependencies=[Depends(ai_rate_limit)])
async def suggest_bullet_variants(cid: UUID, placement_id: UUID, req: AiVariantRequest, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        inputs, error = await load_variant_inputs(c, u["id"], cid, placement_id, req.job_id)
    if error == "resume":
        raise HTTPException(404, "Resume not found")
    if error == "placement":
        raise HTTPException(404, "Bullet not found")
    if error:
        raise HTTPException(404, "Job description not found")
    category = "tool" if is_skill_keyword(req.keyword, req.category) else (req.category or category_for_term(req.keyword) or "")
    job_terms = job_tool_terms(inputs["description"]) if inputs["description"] else []
    result = await suggest_variants(
        inputs["original"],
        inputs["description"],
        req.requirement,
        req.keyword,
        category,
        req.goal,
        job_terms,
        placement_id=str(placement_id),
        job_id=str(req.job_id or ""),
        incorporate_keyword=req.incorporate_keyword,
        max_chars=req.max_chars,
    )
    return {**result, "original": inputs["original"], "category": category}


def _keyword_category(keyword: str, category: str) -> str:
    return "tool" if is_skill_keyword(keyword, category) else (category or category_for_term(keyword) or "")


@app.post("/api/compositions/{cid}/ai-variant-pick", response_model=VariantPick, dependencies=[Depends(ai_rate_limit)])
async def pick_bullet_variants(cid: UUID, req: VariantPickRequest, identity: CurrentUser = Depends(resolve_current_user)):
    """Rank library wording for the listed placements, or every placed bullet, against one job."""
    async with connection() as c:
        u = await owner(identity, c)
        inputs, error = await load_pick_inputs(c, u["id"], cid, req.job_id, req.placement_ids)
    if error == "resume":
        raise HTTPException(404, "Resume not found")
    if error == "placement":
        raise HTTPException(404, "Bullet not found")
    if error:
        raise HTTPException(404, "Job description not found")
    return await pick_variants(
        inputs["description"],
        inputs["placements"],
        inputs["library"],
        inputs["revision"],
        use_ai=req.use_ai,
        placed_ids=inputs["placed_bullet_ids"],
    )


@app.post("/api/compositions/{cid}/ai-keyword-assist", response_model=KeywordAssist, dependencies=[Depends(ai_rate_limit)])
async def keyword_assist(cid: UUID, req: KeywordAssistRequest, identity: CurrentUser = Depends(resolve_current_user)):
    inputs = await _review_inputs(req.job_id, cid, identity)
    return await assist_keyword(
        inputs["description"],
        inputs["resume"],
        inputs["bullets"],
        req.keyword,
        req.requirement,
        _keyword_category(req.keyword, req.category),
        inputs["revision"],
        job_id=str(req.job_id),
    )


ENTRY_TARGETS = {
    "work_experience": "experience",
    "projects": "projects",
    "leadership": "leadership",
}


@app.post("/api/compositions/{cid}/ai-keyword-assist/accept-new", response_model=CompositionState)
async def accept_keyword_bullet(cid: UUID, req: KeywordBulletAccept, identity: CurrentUser = Depends(resolve_current_user)):
    body = " ".join(req.body.split())
    if PLACEHOLDER.search(body):
        raise HTTPException(422, "Replace the [placeholders] with your own details before saving.")
    async with connection() as c:
        u = await owner(identity, c)
        section, error = await load_entry_section(c, u["id"], cid, req.parent_id)
        if error == "resume":
            raise HTTPException(404, "Resume not found")
        if error:
            raise HTTPException(404, "Entry not found")
        ai = None
        if req.source != "own" and req.job_id:
            if not await get_job_description(c, u["id"], req.job_id):
                raise HTTPException(404, "Job description not found")
            # Only text this server handed out, unchanged, counts as AI-written.
            served = issued_draft(new_bullet_key(req.parent_id), body, str(req.job_id))
            generated = req.source == "draft" and served is not None
            ai = {"generated": generated, "model": served or req.model or None, "job_id": req.job_id}
        payload = BulletCreateAndPlace(
            revision=req.revision,
            body=body,
            library_section=ENTRY_TARGETS[section],
            destination_section=section,
            destination_parent_type="content_item",
            destination_parent_id=req.parent_id,
        )
        row, error = await create_and_place(c, u["id"], cid, payload, ai=ai)
        return _placement_result(row, error)


@app.post("/api/compositions/{cid}/bullet-placements/{placement_id}/ai-variants/accept", response_model=CompositionState)
async def accept_bullet_variant(cid: UUID, placement_id: UUID, req: AiVariantAccept, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        ai = None
        if req.source != "own":
            if req.job_id and not await get_job_description(c, u["id"], req.job_id):
                raise HTTPException(404, "Job description not found")
            # Only text this server handed out, unchanged, counts as AI-written.
            served = issued_draft(str(placement_id), req.body, str(req.job_id or ""))
            generated = req.source == "draft" and served is not None
            ai = {"generated": generated, "model": served or req.model or None, "job_id": req.job_id}
        row, error = await save_bullet_edit(
            c, u["id"], cid, placement_id, req.revision, req.body, "variant", name=req.name, ai=ai
        )
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        if not row:
            raise HTTPException(404, "Bullet not found")
        return state(row)


@app.post("/api/compositions/{cid}/ai-condense", response_model=CondenseResult, dependencies=[Depends(ai_rate_limit)])
async def condense_composition(cid: UUID, req: CondenseRequest, identity: CurrentUser = Depends(resolve_current_user)):
    """Suggest bullets to condense and bullets or entries to remove so the resume fits its pages."""
    async with connection() as c:
        u = await owner(identity, c)
        inputs, error = await load_condense_inputs(c, u["id"], cid, req.job_id)
    if error == "resume":
        raise HTTPException(404, "Resume not found")
    if error:
        raise HTTPException(404, "Job description not found")
    return await condense_resume(
        inputs["description"],
        inputs["bullets"],
        inputs["entries"],
        req.bullet_lines,
        req.item_lines,
        req.chars_per_line,
        req.lines_over,
        inputs["revision"],
        use_ai=req.use_ai,
        job_id=str(req.job_id or ""),
    )


@app.post("/api/compositions/{cid}/ai-condense/apply", response_model=CompositionState)
async def apply_condense_changes(cid: UUID, req: CondenseApply, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        if req.job_id and not await get_job_description(c, u["id"], req.job_id):
            raise HTTPException(404, "Job description not found")
        provenance = {}
        for rewrite in req.rewrites:
            # Only text this server handed out, unchanged, counts as AI-written.
            served = issued_draft(str(rewrite.placement_id), rewrite.body, str(req.job_id or ""))
            generated = rewrite.source == "draft" and served is not None
            provenance[str(rewrite.placement_id)] = {
                "generated": generated,
                "model": served or rewrite.model or None,
                "job_id": req.job_id,
            }
        row, error = await apply_condense(c, u["id"], cid, req, provenance)
        if error == "invalid":
            raise HTTPException(422, "A bullet can't be both condensed and removed.")
        return _placement_result(row, error)


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
        return HTMLResponse(render_resume(materialized["resume"],True,materialized["renderer_contract_version"],materialized.get("section_sort_modes",{}),materialized.get("date_format","long"),materialized.get("template_style","classic"),materialized.get("skill_row_max",4)))

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
    html=render_resume(materialized["resume"],False,materialized["renderer_contract_version"],materialized.get("section_sort_modes",{}),materialized.get("date_format","long"),materialized.get("template_style","classic"),materialized.get("skill_row_max",4))
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
    if actual != preferred:
        raise HTTPException(409,f"Export blocked: resume is {actual} pages; target length is {preferred}.")
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

@app.get("/api/job-descriptions", response_model=list[JobDescriptionRecord])
async def job_descriptions(identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        return await list_job_descriptions(c, u["id"])


@app.post("/api/job-descriptions", response_model=JobDescriptionRecord, status_code=201)
async def add_job_description(
    req: JobDescriptionWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await create_job_description(c, u["id"], req)
        if error == "resume":
            raise HTTPException(404, "Resume not found")
        return row


@app.get("/api/job-descriptions/{job_id}", response_model=JobDescriptionRecord)
async def job_description(job_id: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row = await get_job_description(c, u["id"], job_id)
        if not row:
            raise HTTPException(404, "Job description not found")
        return row


@app.put("/api/job-descriptions/{job_id}", response_model=JobDescriptionRecord)
async def edit_job_description(
    job_id: UUID,
    req: JobDescriptionWrite,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await update_job_description(c, u["id"], job_id, req)
        if error == "resume":
            raise HTTPException(404, "Resume not found")
        if error:
            raise HTTPException(404, "Job description not found")
        return row


@app.post("/api/job-descriptions/{job_id}/archive", response_model=JobDescriptionRecord)
async def archive_job(job_id: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row = await archive_job_description(c, u["id"], job_id)
        if not row:
            raise HTTPException(404, "Job description not found")
        return row


async def _compare_job(job_id: UUID, composition_id: UUID, identity: CurrentUser):
    async with connection() as c:
        u = await owner(identity, c)
        result, error = await compare_job_description(c, u["id"], job_id, composition_id)
        if error == "resume":
            raise HTTPException(404, "Resume not found")
        if error:
            raise HTTPException(404, "Job description not found")
        return result


@app.get("/api/job-descriptions/{job_id}/analysis", response_model=JobAnalysis)
async def job_description_analysis(job_id: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        result = await analyze_job_description(c, u["id"], job_id)
        if not result:
            raise HTTPException(404, "Job description not found")
        return result


@app.get("/api/job-descriptions/{job_id}/match", response_model=JobMatch)
async def match_job_description(
    job_id: UUID,
    composition_id: UUID = Query(),
    identity: CurrentUser = Depends(resolve_current_user),
):
    return await _compare_job(job_id, composition_id, identity)


@app.post("/api/job-descriptions/{job_id}/match", response_model=JobMatch)
async def match_job_description_post(
    job_id: UUID,
    req: JobMatchRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    return await _compare_job(job_id, req.composition_id, identity)


@app.post("/api/job-descriptions/{job_id}/ai-review", response_model=AiReview, dependencies=[Depends(ai_rate_limit)])
async def ai_review_job(
    job_id: UUID,
    req: JobMatchRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    async with connection() as c:
        u = await owner(identity, c)
        inputs, error = await load_ai_review_inputs(c, u["id"], job_id, req.composition_id)
        user_id = u["id"]
    if error == "resume":
        raise HTTPException(404, "Resume not found")
    if error:
        raise HTTPException(404, "Job description not found")
    result = await review_resume(
        req.composition_id,
        inputs["description"],
        inputs["resume"],
        inputs["bullets"],
        inputs["review"],
        inputs["revision"],
    )
    async with connection() as c:
        await link_job_composition(c, user_id, job_id, req.composition_id)
    return result


async def _review_inputs(job_id: UUID, composition_id: UUID, identity: CurrentUser):
    async with connection() as c:
        u = await owner(identity, c)
        inputs, error = await load_ai_review_inputs(c, u["id"], job_id, composition_id)
    if error == "resume":
        raise HTTPException(404, "Resume not found")
    if error:
        raise HTTPException(404, "Job description not found")
    return inputs


@app.post("/api/job-descriptions/{job_id}/ai-coach", response_model=CoachResult, dependencies=[Depends(ai_rate_limit)])
async def ai_coach_job(job_id: UUID, req: JobMatchRequest, identity: CurrentUser = Depends(resolve_current_user)):
    inputs = await _review_inputs(job_id, req.composition_id, identity)
    return await coach_resume(
        inputs["description"],
        inputs["resume"],
        inputs["bullets"],
        inputs["review"],
        inputs["revision"],
        job_id=str(job_id),
    )


@app.post("/api/compositions/{cid}/ai-chat", response_model=ChatTurn, dependencies=[Depends(ai_rate_limit)])
async def ai_chat(cid: UUID, req: ChatRequest, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        inputs, error = await load_chat_inputs(c, u["id"], cid, req.job_id)
    if error == "resume":
        raise HTTPException(404, "Resume not found")
    if error:
        raise HTTPException(404, "Job description not found")
    return await chat_turn(
        [message.model_dump() for message in req.messages],
        inputs["description"],
        inputs["resume"],
        inputs["bullets"],
        inputs["review"],
        inputs["library"],
        inputs["revision"],
        job_id=str(req.job_id or ""),
    )


@app.post("/api/job-descriptions/{job_id}/define", response_model=KeywordDefinition, dependencies=[Depends(ai_rate_limit)])
async def define_job_keyword(job_id: UUID, req: KeywordDefineRequest, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        job = await get_job_description(c, u["id"], job_id)
    if not job:
        raise HTTPException(404, "Job description not found")
    return await define_keyword(job["body"], req.keyword, req.requirement)


@app.post("/api/job-descriptions/{job_id}/ats-score", response_model=AtsScore)
async def ats_score_job(job_id: UUID, req: AtsScoreRequest, identity: CurrentUser = Depends(resolve_current_user)):
    inputs = await _review_inputs(job_id, req.composition_id, identity)
    match = match_qualifications(inputs["description"], inputs["resume"], inputs["bullets"], inputs["review"])
    result = score_resume(match, inputs["resume"], inputs["job"], inputs["composition"], req.page_count)
    return {**result, "revision": inputs["revision"]}


if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")





