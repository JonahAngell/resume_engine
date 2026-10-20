"""Compositions API routes."""

import os
from uuid import UUID
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from ..database import (
    connection,
)
from ..editing_repository import (
    duplicate,
    get_revision,
    list_revisions,
    restore_revision,
    save_composition,
    select_historical,
    update_composition_metadata,
    set_composition_archive,
)
from ..editing_schemas import (
    AiVariantAccept,
    BulletPlacementReplaceMany,
    CondenseApply,
    KeywordBulletAccept,
    SkillAddWrite,
    SkillRecommendRequest,
    CompositionCreate,
    CompositionItemSelection,
    ToolVisibilityWrite,
    ToolOrderWrite,
    CompositionSave,
    CompositionState,
    DuplicateComposition,
    RestoreRevision,
    CompositionMetadataWrite,
    CompositionLifecycleWrite,
    BulletPlacementWrite, BulletCreateAndPlace, BulletPlacementReplace,
    BulletPlacementReorder, BulletUsageUpdate, CompositionPreferencesWrite,
    EntryCreateWrite,
    BulletSaveChoice,
    EntrySaveChoice,
    SummarySaveChoice,
    ProfileSaveChoice,
)
from ..resume_variants import (
    save_bullet_edit,
    save_entry_edit,
    save_profile_edit,
    save_summary_edit,
)
from .. import default_sets
from ..identity import CurrentUser, resolve_current_user
from ..library_repository import (
    add_skill_to_resume,
    load_skill_inputs,
    load_composition,
    select_interest,
    select_profile,
    select_summary,
    select_tool_group,
    hidden_tools,
    set_tool_visibility,
    tool_order,
    set_tool_order,
    save_sections_panel,
    reorder_composition_items,
    select_education,
    composition_items,
    create_and_include_entry,
)
from ..library_schemas import (
    CompositionInterestSelection,
    CompositionProfileSelection,
    CompositionSummarySelection,
    CompositionSectionsWrite,
    CompositionItemOrderWrite,
)
from ..ai_keyword import PLACEHOLDER, new_bullet_key
from ..ai_variants import issued_draft
from ..skill_groups import recommend_group, recommend_with_ai
from ..job_repository import (
    get_job_description,
    load_entry_section,
)
from ..phase2j_repository import (
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
from ..phase2l_repository import update_preferences
from ..phase2m_repository import materialize_composition, materialize_revision
from ..rate_limit import limiter
from ..render import render_resume
from ..schemas import Resume
from ..api_common import ENTRY_TARGETS, _pdf_page_count, _placement_result, _safe_filename, build_resume, found, owner, state

router = APIRouter()


@router.get("/api/compositions/{cid}/tool-order")
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


@router.put(
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


@router.get("/api/compositions/{cid}/hidden-tools")
async def composition_hidden_tools(
    cid: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        rows = await hidden_tools(c, u["id"], cid)
        if rows is None:
            raise HTTPException(404, "Composition not found")
        return [{"tool_id": str(row["tool_id"])} for row in rows]


@router.put("/api/compositions/{cid}/tools/{tool_id}", response_model=CompositionState)
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


@router.put("/api/compositions/{cid}/education", response_model=CompositionState)
async def choose_education(cid: UUID, req: CompositionItemSelection, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c);row,error=await select_education(c,u["id"],cid,req.revision,req.item_id,req.included)
        if error=="missing": raise HTTPException(404,"Composition or education item not found")
        if error=="stale": raise HTTPException(409,"Composition changed; reload before saving")
        return state(row)


@router.put("/api/compositions/{cid}/tool-groups", response_model=CompositionState)
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


@router.post("/api/compositions/{cid}/skills/recommend")
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


@router.post("/api/compositions/{cid}/skills", response_model=CompositionState)
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


@router.put(
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


@router.put("/api/compositions/{cid}/sections", response_model=CompositionState)
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


@router.get("/api/compositions/{cid}/items")
async def get_composition_items(cid: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); rows=await composition_items(c,u["id"],cid)
        if rows is None: raise HTTPException(404,"Composition not found")
        return rows


@router.post("/api/compositions/{cid}/entries/create", response_model=CompositionState, status_code=201)
async def create_composition_entry(cid: UUID, req: EntryCreateWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await create_and_include_entry(c,u["id"],cid,req)
        if error=="missing": raise HTTPException(404,"Resource not found")
        if error=="stale": raise HTTPException(409,"Composition changed; reload before saving")
        if error=="invalid": raise HTTPException(422,"Unsupported entry section")
        return state(row)


@router.put("/api/compositions/{cid}/items/order", response_model=CompositionState)
async def order_composition_items(cid: UUID, req: CompositionItemOrderWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await reorder_composition_items(c, u["id"], cid, req)
        if error == "stale": raise HTTPException(409, "Composition changed; reload before saving")
        if error == "missing": raise HTTPException(404, "Resource not found")
        if error == "invalid": raise HTTPException(422, "Invalid selected-item order")
        return state(row)


@router.post("/api/compositions", response_model=CompositionState, status_code=201)
async def new_comp(
    req: CompositionCreate, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        set_id = req.default_set_id
        if set_id is None and not req.entire_library:
            default = await default_sets.default_set(c, u["id"])
            set_id = default["id"] if default else None
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


@router.post("/api/compositions/{cid}/bullet-placements/{placement_id}/save", response_model=CompositionState)
async def save_bullet_choice(cid: UUID, placement_id: UUID, req: BulletSaveChoice, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await save_bullet_edit(c, u["id"], cid, placement_id, req.revision, req.body, req.mode)
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        if not row:
            raise HTTPException(404, "Bullet not found")
        return state(row)


@router.post("/api/compositions/{cid}/entries/{item_id}/save", response_model=CompositionState)
async def save_entry_choice(cid: UUID, item_id: UUID, req: EntrySaveChoice, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await save_entry_edit(c, u["id"], cid, item_id, req.revision, req.section, req.fields, req.mode)
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        if not row:
            raise HTTPException(404, "Entry not found")
        return state(row)


@router.post("/api/compositions/{cid}/summaries/{summary_id}/save", response_model=CompositionState)
async def save_summary_choice(cid: UUID, summary_id: UUID, req: SummarySaveChoice, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await save_summary_edit(c, u["id"], cid, summary_id, req.revision, req.name, req.body, req.mode)
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        if not row:
            raise HTTPException(404, "Summary not found")
        return state(row)


@router.post("/api/compositions/{cid}/profiles/{profile_id}/save", response_model=CompositionState)
async def save_profile_choice(cid: UUID, profile_id: UUID, req: ProfileSaveChoice, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await save_profile_edit(c, u["id"], cid, profile_id, req.revision, req.fields, req.mode)
        if error == "stale":
            raise HTTPException(409, "Composition changed; reload before saving")
        if not row:
            raise HTTPException(404, "Profile not found")
        return state(row)


@router.get("/api/compositions/{cid}", response_model=CompositionState)
async def get_comp(cid: UUID, include_archived: bool = False, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row = await load_composition(c, u["id"], cid, include_archived)
        return state(found(row, "Composition not found"))


@router.put("/api/compositions/{cid}/metadata", response_model=CompositionState)
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


@router.post("/api/compositions/{cid}/archive", response_model=CompositionState)
async def archive_composition(cid: UUID, req: CompositionLifecycleWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c);row,error=await set_composition_archive(c,u["id"],cid,req.revision,True)
        if error=="missing": raise HTTPException(404,"Composition not found")
        if error=="stale": raise HTTPException(409,"Composition changed; reload before saving")
        return state(row)


@router.post("/api/compositions/{cid}/restore", response_model=CompositionState)
async def restore_composition(cid: UUID, req: CompositionLifecycleWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c);row,error=await set_composition_archive(c,u["id"],cid,req.revision,False)
        if error=="missing": raise HTTPException(404,"Composition not found")
        if error=="stale": raise HTTPException(409,"Composition changed; reload before saving")
        return state(row)


@router.put("/api/compositions/{cid}", response_model=CompositionState)
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


@router.put("/api/compositions/{cid}/preferences", response_model=CompositionState)
async def composition_preferences(cid: UUID, req: CompositionPreferencesWrite, identity: CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await update_preferences(c,u["id"],cid,req)
        if error=="missing": raise HTTPException(404,"Composition not found")
        if error=="stale": raise HTTPException(409,"Composition changed; reload before saving")
        return state(row)


@router.put("/api/compositions/{cid}/profile", response_model=CompositionState)
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


@router.put("/api/compositions/{cid}/summary", response_model=CompositionState)
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


@router.put("/api/compositions/{cid}/interests", response_model=CompositionState)
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


@router.post(
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
            return state(found(row, "Composition not found"))
    except HTTPException:
        raise
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(409, "A composition with that name already exists")
        raise


@router.get("/api/compositions/{cid}/revisions")
async def revisions(cid: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        return await list_revisions(c, u["id"], cid)


@router.get("/api/compositions/{cid}/revisions/{rid}")
async def revision(
    cid: UUID, rid: UUID, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row = await get_revision(c, u["id"], cid, rid)
        return found(row, "Revision not found")


@router.post(
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


@router.get("/api/compositions/{cid}/revisions/{rid}/render",response_class=HTMLResponse)
async def render_revision(cid:UUID,rid:UUID,identity:CurrentUser=Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c);materialized,error=await materialize_revision(c,u["id"],cid,rid)
        if error:raise HTTPException(404,"Revision not found")
        return HTMLResponse(render_resume(materialized["resume"],True,materialized["renderer_contract_version"],materialized["section_sort_modes"],materialized["date_format"],materialized.get("template_style","classic"),materialized.get("skill_row_max",4)))


@router.get("/api/compositions/{cid}/bullet-placements")
async def bullet_placements(cid: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c)
        if not await load_composition(c,u["id"],cid): raise HTTPException(404,"Composition not found")
        return await usage_rows(c,u["id"],cid)


@router.post("/api/compositions/{cid}/bullet-placements", response_model=CompositionState)
async def add_bullet_placement(cid: UUID, req: BulletPlacementWrite, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await insert_placement(c,u["id"],cid,req)
        return _placement_result(row,error)


@router.post("/api/compositions/{cid}/bullet-placements/create", response_model=CompositionState)
async def create_bullet_placement(cid: UUID, req: BulletCreateAndPlace, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await create_and_place(c,u["id"],cid,req)
        return _placement_result(row,error)


@router.post("/api/compositions/{cid}/bullet-placements/replace-many", response_model=CompositionState)
async def change_bullet_placements(cid: UUID, req: BulletPlacementReplaceMany, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await replace_placements(c,u["id"],cid,req)
        return _placement_result(row,error)


@router.put("/api/compositions/{cid}/bullet-placements/order", response_model=CompositionState)
async def order_bullet_placements(cid: UUID, req: BulletPlacementReorder, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await reorder_placements(c,u["id"],cid,req)
        return _placement_result(row,error)


@router.delete("/api/compositions/{cid}/bullet-placements/{placement_id}", response_model=CompositionState)
async def delete_bullet_placement(cid: UUID, placement_id: UUID, revision: int = Query(..., ge=1), identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await remove_placement(c,u["id"],cid,placement_id,revision)
        return _placement_result(row,error)


@router.put("/api/compositions/{cid}/bullet-placements/{placement_id}", response_model=CompositionState)
async def change_bullet_placement(cid: UUID, placement_id: UUID, req: BulletPlacementReplace, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await replace_placement(c,u["id"],cid,placement_id,req)
        return _placement_result(row,error)


@router.post("/api/compositions/{cid}/bullet-placements/{placement_id}/update-usage", response_model=CompositionState)
async def refresh_bullet_usage(cid: UUID, placement_id: UUID, req: BulletUsageUpdate, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c); row,error=await update_usage(c,u["id"],cid,placement_id,req.revision)
        return _placement_result(row,error)


@router.post("/api/compositions/{cid}/ai-keyword-assist/accept-new", response_model=CompositionState)
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


@router.post("/api/compositions/{cid}/bullet-placements/{placement_id}/ai-variants/accept", response_model=CompositionState)
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


@router.post("/api/compositions/{cid}/ai-condense/apply", response_model=CompositionState)
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


@router.post("/api/render", response_class=HTMLResponse)
def render(payload: Resume, identity: CurrentUser = Depends(resolve_current_user)):
    # Compatibility-only preview. Secure export never accepts this payload.
    return HTMLResponse(render_resume(payload, True))


@router.get("/api/compositions/{cid}/render", response_class=HTMLResponse)
async def render_composition(cid: UUID, revision: int | None = None, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u=await owner(identity,c)
        materialized,error=await materialize_composition(c,u["id"],cid,revision)
        if error=="stale": raise HTTPException(409,"Composition changed; reload before rendering")
        if error: raise HTTPException(404,"Composition not found")
        return HTMLResponse(render_resume(materialized["resume"],True,materialized["renderer_contract_version"],materialized.get("section_sort_modes",{}),materialized.get("date_format","long"),materialized.get("template_style","classic"),materialized.get("skill_row_max",4)))


@router.post("/api/compositions/{cid}/export/pdf")
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


@router.post("/api/export/pdf")
async def raw_export_disabled(payload: Resume, identity: CurrentUser = Depends(resolve_current_user)):
    raise HTTPException(410,"Raw-payload export is disabled. Export an owned composition instead.")
