"""Helpers shared by the API routers."""

from pathlib import Path
from uuid import UUID
from fastapi import HTTPException
from .database import (
    connection,
)
from .editing_repository import (
    create_composition,
    update_composition_metadata,
)
from .resume_variants import (
    apply_library_selection,
)
from .identity import CurrentUser
from .library_repository import (
    ensure_user,
)
from .job_match import is_skill_keyword
from .related_skills import category_for_term
from .job_repository import (
    compare_job_description,
    get_job_description,
    load_ai_review_inputs,
)
from .schemas import Resume


ROOT = Path(__file__).resolve().parents[2]


SEED = ROOT / "seed" / "nia-calder-resume.json"


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


def found(value, detail: str):
    """Return `value`, or raise 404 with `detail` when it is empty."""
    if not value:
        raise HTTPException(404, detail)
    return value


MAX_IMPORT_BYTES = 10 * 1024 * 1024


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


def _placement_result(row, error):
    if error == "missing": raise HTTPException(404, "Resource not found")
    if error == "stale": raise HTTPException(409, "Composition changed; reload before saving")
    if error == "invalid": raise HTTPException(422, "Invalid placement order")
    if error == "duplicate": raise HTTPException(409, "This bullet is already in this resume.")
    if error == "section": raise HTTPException(422, "This bullet belongs to a different section.")
    return state(row)


def _keyword_category(keyword: str, category: str) -> str:
    return "tool" if is_skill_keyword(keyword, category) else (category or category_for_term(keyword) or "")


ENTRY_TARGETS = {
    "work_experience": "experience",
    "projects": "projects",
    "leadership": "leadership",
}


def _pdf_page_count(content: bytes) -> int:
    import re
    return len(re.findall(rb"/Type\s*/Page\b", content))


def _safe_filename(value: str) -> str:
    import re
    value=re.sub(r"[^A-Za-z0-9._ -]+","",value).strip(" .")
    return (value or "resume")[:100]+".pdf"


async def _compare_job(job_id: UUID, composition_id: UUID, identity: CurrentUser):
    async with connection() as c:
        u = await owner(identity, c)
        result, error = await compare_job_description(c, u["id"], job_id, composition_id)
        if error == "resume":
            raise HTTPException(404, "Resume not found")
        if error:
            raise HTTPException(404, "Job description not found")
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
