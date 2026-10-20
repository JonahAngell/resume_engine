"""Jobs API routes."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from ..database import (
    connection,
)
from ..editing_schemas import (
    AtsScoreRequest,
)
from ..identity import CurrentUser, resolve_current_user
from ..ai_schemas import AtsScore
from ..ats_score import score_resume
from ..job_match import match_qualifications
from ..job_repository import (
    analyze_job_description,
    archive_job_description,
    create_job_description,
    get_job_description,
    list_job_descriptions,
    update_job_description,
)
from ..job_schemas import (
    JobAnalysis,
    JobDescriptionRecord,
    JobDescriptionWrite,
    JobMatch,
    JobMatchRequest,
)
from ..api_common import _compare_job, _review_inputs, owner

router = APIRouter()


@router.get("/api/job-descriptions", response_model=list[JobDescriptionRecord])
async def job_descriptions(identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        return await list_job_descriptions(c, u["id"])


@router.post("/api/job-descriptions", response_model=JobDescriptionRecord, status_code=201)
async def add_job_description(
    req: JobDescriptionWrite, identity: CurrentUser = Depends(resolve_current_user)
):
    async with connection() as c:
        u = await owner(identity, c)
        row, error = await create_job_description(c, u["id"], req)
        if error == "resume":
            raise HTTPException(404, "Resume not found")
        return row


@router.get("/api/job-descriptions/{job_id}", response_model=JobDescriptionRecord)
async def job_description(job_id: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row = await get_job_description(c, u["id"], job_id)
        if not row:
            raise HTTPException(404, "Job description not found")
        return row


@router.put("/api/job-descriptions/{job_id}", response_model=JobDescriptionRecord)
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


@router.post("/api/job-descriptions/{job_id}/archive", response_model=JobDescriptionRecord)
async def archive_job(job_id: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        row = await archive_job_description(c, u["id"], job_id)
        if not row:
            raise HTTPException(404, "Job description not found")
        return row


@router.get("/api/job-descriptions/{job_id}/analysis", response_model=JobAnalysis)
async def job_description_analysis(job_id: UUID, identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        u = await owner(identity, c)
        result = await analyze_job_description(c, u["id"], job_id)
        if not result:
            raise HTTPException(404, "Job description not found")
        return result


# Matching is POST only: it records which resume the job was last compared with,
# so it must not be reachable by a cross-site GET.
@router.post("/api/job-descriptions/{job_id}/match", response_model=JobMatch)
async def match_job_description_post(
    job_id: UUID,
    req: JobMatchRequest,
    identity: CurrentUser = Depends(resolve_current_user),
):
    return await _compare_job(job_id, req.composition_id, identity)


@router.post("/api/job-descriptions/{job_id}/ats-score", response_model=AtsScore)
async def ats_score_job(job_id: UUID, req: AtsScoreRequest, identity: CurrentUser = Depends(resolve_current_user)):
    inputs = await _review_inputs(job_id, req.composition_id, identity)
    match = match_qualifications(inputs["description"], inputs["resume"], inputs["bullets"], inputs["review"])
    result = score_resume(match, inputs["resume"], inputs["job"], inputs["composition"], req.page_count)
    return {**result, "revision": inputs["revision"]}
