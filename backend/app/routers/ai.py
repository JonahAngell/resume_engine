"""Ai API routes."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from ..database import (
    connection,
)
from ..editing_schemas import (
    AiVariantRequest,
    VariantPickRequest,
    CondenseRequest,
    KeywordAssistRequest,
    KeywordDefineRequest,
)
from ..ai_recommend import recommend_resume
from ..identity import CurrentUser, resolve_current_user
from ..library_repository import (
    fetch_library,
)
from ..ai_review import review_resume
from ..ai_schemas import AiReview, ChatRequest, ChatTurn, CoachResult, KeywordAssist, KeywordDefinition, ResumeRecommendRequest, ResumeRecommendResult, VariantPick, VariantSuggestions
from ..ai_define import define_keyword
from ..ai_variant_pick import pick_variants
from ..ai_condense import condense_resume
from ..ai_schemas import CondenseResult
from ..ai_chat import chat_turn
from ..ai_coach import coach_resume
from ..ai_keyword import assist_keyword
from ..ai_variants import job_tool_terms, suggest_variants
from ..job_match import is_skill_keyword
from ..related_skills import category_for_term
from ..job_repository import (
    get_job_description,
    link_job_composition,
    load_ai_review_inputs,
    load_chat_inputs,
    load_pick_inputs,
    load_condense_inputs,
    load_variant_inputs,
)
from ..job_schemas import (
    JobMatchRequest,
)
from ..rate_limit import ai_rate_limit
from ..api_common import _keyword_category, _review_inputs, build_resume, owner, state

router = APIRouter()


@router.post("/api/compositions/ai-recommend", response_model=ResumeRecommendResult, status_code=201, dependencies=[Depends(ai_rate_limit)])
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


@router.post("/api/compositions/{cid}/bullet-placements/{placement_id}/ai-variants", response_model=VariantSuggestions, dependencies=[Depends(ai_rate_limit)])
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


@router.post("/api/compositions/{cid}/ai-variant-pick", response_model=VariantPick, dependencies=[Depends(ai_rate_limit)])
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


@router.post("/api/compositions/{cid}/ai-keyword-assist", response_model=KeywordAssist, dependencies=[Depends(ai_rate_limit)])
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


@router.post("/api/compositions/{cid}/ai-condense", response_model=CondenseResult, dependencies=[Depends(ai_rate_limit)])
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


@router.post("/api/job-descriptions/{job_id}/ai-review", response_model=AiReview, dependencies=[Depends(ai_rate_limit)])
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


@router.post("/api/job-descriptions/{job_id}/ai-coach", response_model=CoachResult, dependencies=[Depends(ai_rate_limit)])
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


@router.post("/api/compositions/{cid}/ai-chat", response_model=ChatTurn, dependencies=[Depends(ai_rate_limit)])
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


@router.post("/api/job-descriptions/{job_id}/define", response_model=KeywordDefinition, dependencies=[Depends(ai_rate_limit)])
async def define_job_keyword(job_id: UUID, req: KeywordDefineRequest, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        job = await get_job_description(c, u["id"], job_id)
    if not job:
        raise HTTPException(404, "Job description not found")
    return await define_keyword(job["body"], req.keyword, req.requirement)
