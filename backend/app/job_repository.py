import json
from uuid import UUID

from psycopg.rows import dict_row

from .job_match import analyze_requirements, extract_facts, match_qualifications
from .library_repository import load_composition

COLUMNS = "id, company, role, title, body, composition_id, keyword_review, archived_at, created_at, updated_at"
SECTION_LABELS = {
    "work_experience": "Work Experience",
    "projects": "Projects",
    "education": "Education",
    "leadership": "Leadership",
    "tool_groups": "Skills",
    "personal_interests": "Personal Interests",
    "custom_sections": "Custom",
}


def _normalize(row):
    if not row or "keyword_review" not in row:
        return row
    review = row["keyword_review"] or {}
    if isinstance(review, str):
        review = json.loads(review)
    if not isinstance(review, dict):
        review = {}
    row["keyword_review"] = {
        "dismissed": list(review.get("dismissed") or []),
        "added": list(review.get("added") or []),
        "matched": list(review.get("matched") or []),
    }
    facts = extract_facts(row.get("body") or "")
    row["salary"] = facts["salary"]
    row["locations"] = facts["locations"]
    return row


async def _one(conn, query, params=()):
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(query, params)
        return _normalize(await cursor.fetchone())


async def _many(conn, query, params=()):
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(query, params)
        return [_normalize(row) for row in await cursor.fetchall()]


def _review_json(payload) -> str | None:
    if payload.keyword_review is None:
        return None
    return json.dumps(payload.keyword_review.model_dump())


def _title(company: str, role: str, title: str, body: str) -> str:
    if title.strip():
        return title.strip()[:300]
    label = " — ".join(part for part in (company.strip(), role.strip()) if part)
    if not label:
        label = body.strip().splitlines()[0].strip()
    return label[:300].strip() or "Job description"


async def _composition_owned(conn, user_id, composition_id) -> bool:
    if composition_id is None:
        return True
    row = await _one(
        conn,
        "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s",
        (composition_id, user_id),
    )
    return row is not None


async def list_job_descriptions(conn, user_id):
    return await _many(
        conn,
        f"SELECT {COLUMNS} FROM job_descriptions WHERE user_id=%s AND archived_at IS NULL ORDER BY updated_at DESC, id",
        (user_id,),
    )


async def get_job_description(conn, user_id, job_id):
    return await _one(
        conn,
        f"SELECT {COLUMNS} FROM job_descriptions WHERE id=%s AND user_id=%s AND archived_at IS NULL",
        (job_id, user_id),
    )


async def create_job_description(conn, user_id, payload):
    if not await _composition_owned(conn, user_id, payload.composition_id):
        return None, "resume"
    title = _title(payload.company, payload.role, payload.title, payload.body)
    row = await _one(
        conn,
        f"""INSERT INTO job_descriptions (user_id, company, role, title, body, composition_id, keyword_review)
            VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s::jsonb, '{{}}'::jsonb))
            RETURNING {COLUMNS}""",
        (
            user_id,
            payload.company,
            payload.role,
            title,
            payload.body,
            payload.composition_id,
            _review_json(payload),
        ),
    )
    return row, None


async def update_job_description(conn, user_id, job_id, payload):
    async with conn.transaction():
        if not await get_job_description(conn, user_id, job_id):
            return None, "missing"
        if not await _composition_owned(conn, user_id, payload.composition_id):
            return None, "resume"
        title = _title(payload.company, payload.role, payload.title, payload.body)
        row = await _one(
            conn,
            f"""UPDATE job_descriptions
                SET company=%s, role=%s, title=%s, body=%s, composition_id=%s,
                    keyword_review=COALESCE(%s::jsonb, keyword_review), updated_at=now()
                WHERE id=%s AND user_id=%s AND archived_at IS NULL
                RETURNING {COLUMNS}""",
            (
                payload.company,
                payload.role,
                title,
                payload.body,
                payload.composition_id,
                _review_json(payload),
                job_id,
                user_id,
            ),
        )
        if not row:
            return None, "missing"
        await conn.execute(
            """UPDATE resume_compositions
               SET target_company=%s, target_role=%s
               WHERE job_description_id=%s AND user_id=%s""",
            (row["company"], row["role"], job_id, user_id),
        )
        return row, None


async def archive_job_description(conn, user_id, job_id):
    row = await _one(
        conn,
        f"""UPDATE job_descriptions
            SET archived_at=now(), updated_at=now()
            WHERE id=%s AND user_id=%s AND archived_at IS NULL
            RETURNING {COLUMNS}""",
        (job_id, user_id),
    )
    return row


async def analyze_job_description(conn, user_id, job_id):
    job = await get_job_description(conn, user_id, job_id)
    if not job:
        return None
    review = job.get("keyword_review") or {}
    if isinstance(review, str):
        review = json.loads(review)
    return analyze_requirements(job["body"], review)


async def compare_job_description(conn, user_id, job_id, composition_id: UUID):
    job = await get_job_description(conn, user_id, job_id)
    if not job:
        return None, "missing"
    composition = await load_composition(conn, user_id, composition_id, include_archived=False)
    if not composition:
        return None, "resume"
    payload = composition["render_payload"] or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    review = job.get("keyword_review") or {}
    if isinstance(review, str):
        review = json.loads(review)
    bullets = await _placed_bullets(conn, user_id, composition_id)
    result = match_qualifications(job["body"], payload, bullets, review)
    await _one(
        conn,
        "UPDATE job_descriptions SET composition_id=%s WHERE id=%s AND user_id=%s RETURNING id",
        (composition_id, job_id, user_id),
    )
    result["composition_id"] = composition_id
    return result, None


async def load_ai_review_inputs(conn, user_id, job_id, composition_id: UUID):
    job = await get_job_description(conn, user_id, job_id)
    if not job:
        return None, "missing"
    composition = await load_composition(conn, user_id, composition_id, include_archived=False)
    if not composition:
        return None, "resume"
    payload = composition["render_payload"] or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    review = job.get("keyword_review") or {}
    if isinstance(review, str):
        review = json.loads(review)
    bullets = await _placed_bullets(conn, user_id, composition_id)
    return {
        "description": job["body"],
        "resume": payload,
        "bullets": bullets,
        "review": review,
        "revision": int(composition.get("revision") or 0),
        "job": job,
        "composition": composition,
    }, None


async def link_job_composition(conn, user_id, job_id, composition_id: UUID):
    await _one(
        conn,
        "UPDATE job_descriptions SET composition_id=%s WHERE id=%s AND user_id=%s RETURNING id",
        (composition_id, job_id, user_id),
    )


async def _placed_bullets(conn, user_id, composition_id: UUID):
    rows = await _many(
        conn,
        """SELECT cb.bullet_id::text AS id,
                  cb.id::text AS placement_id,
                  cb.destination_parent_id::text AS parent_id,
                  COALESCE(cb.wording_snapshot, v.body, '') AS wording,
                  COALESCE(cb.destination_section, '') AS section,
                  (ROW_NUMBER() OVER (
                     PARTITION BY cb.destination_parent_id
                     ORDER BY cb.sort_order, cb.id
                  ) - 1)::int AS line_index,
                  COALESCE(
                    json_agg(t.display_name ORDER BY t.normalized_name)
                      FILTER (WHERE t.display_name IS NOT NULL),
                    '[]'::json
                  ) AS tags
           FROM composition_bullets cb
           JOIN bullets b ON b.id = cb.bullet_id AND b.user_id = %s
           LEFT JOIN bullet_variants v ON v.id = cb.variant_id
           LEFT JOIN library_bullet_tags bt ON bt.bullet_id = b.id
           LEFT JOIN library_tags t ON t.id = bt.tag_id AND t.user_id = %s
           WHERE cb.composition_id = %s
           GROUP BY cb.id, cb.bullet_id, cb.destination_parent_id, cb.wording_snapshot, v.body,
                    cb.destination_section, cb.sort_order
           ORDER BY cb.sort_order, cb.id""",
        (user_id, user_id, composition_id),
    )
    placed = []
    for row in rows:
        tags = row["tags"] or []
        if isinstance(tags, str):
            tags = json.loads(tags)
        placed.append(
            {
                "id": row["id"],
                "placement_id": row["placement_id"],
                "parent_id": row["parent_id"],
                "line_index": row["line_index"],
                "wording": row["wording"] or "",
                "section": SECTION_LABELS.get(row["section"], row["section"]),
                "tags": tags,
            }
        )
    return placed


async def load_variant_inputs(conn, user_id, composition_id: UUID, placement_id: UUID, job_id: UUID):
    """The placed bullet's current wording and the job text. The client never supplies the bullet."""
    composition = await load_composition(conn, user_id, composition_id, include_archived=False)
    if not composition:
        return None, "resume"
    placement = await _one(
        conn,
        """SELECT COALESCE(cb.wording_snapshot, v.body, '') AS wording
           FROM composition_bullets cb
           LEFT JOIN bullet_variants v ON v.id = cb.variant_id
           WHERE cb.id = %s AND cb.composition_id = %s""",
        (placement_id, composition_id),
    )
    if not placement:
        return None, "placement"
    job = await get_job_description(conn, user_id, job_id)
    if not job:
        return None, "job"
    return {"original": placement["wording"], "description": job["body"] or ""}, None


async def load_entry_section(conn, user_id, composition_id: UUID, parent_id: UUID):
    """The section of a role or project on this resume, or None when it is not one."""
    composition = await load_composition(conn, user_id, composition_id, include_archived=False)
    if not composition:
        return None, "resume"
    payload = composition["render_payload"] or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    for section in ("work_experience", "projects", "leadership"):
        for entry in payload.get(section) or []:
            if isinstance(entry, dict) and str(entry.get("id") or "") == str(parent_id):
                return section, None
    return None, "entry"
