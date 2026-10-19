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
        "skipped": list(review.get("skipped") or []),
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
                  cb.variant_id::text AS variant_id,
                  cb.destination_parent_id::text AS parent_id,
                  cb.destination_parent_type AS parent_type,
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
           GROUP BY cb.id, cb.bullet_id, cb.variant_id, cb.destination_parent_id, cb.destination_parent_type,
                    cb.wording_snapshot, v.body, cb.destination_section, cb.sort_order
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
                "variant_id": row["variant_id"],
                "parent_id": row["parent_id"],
                "parent_type": row["parent_type"],
                "destination_section": row["section"],
                "line_index": row["line_index"],
                "wording": row["wording"] or "",
                "section": SECTION_LABELS.get(row["section"], row["section"]),
                "tags": tags,
            }
        )
    return placed


async def load_variant_inputs(conn, user_id, composition_id: UUID, placement_id: UUID, job_id: UUID | None):
    """The placed bullet's current wording and the job text ("" without a job). The client never
    supplies the bullet."""
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
    if job_id is None:
        return {"original": placement["wording"], "description": ""}, None
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


CONDENSE_ENTRY_SECTIONS = ("work_experience", "projects", "leadership")


async def load_condense_inputs(conn, user_id, composition_id: UUID, job_id: UUID | None):
    """Placed bullets with their preview line id and parent label, and the included roles,
    projects, and leadership entries. The client never supplies wording."""
    composition = await load_composition(conn, user_id, composition_id, include_archived=False)
    if not composition:
        return None, "resume"
    description = ""
    if job_id is not None:
        job = await get_job_description(conn, user_id, job_id)
        if not job:
            return None, "job"
        description = job["body"] or ""
    bullets = await _many(
        conn,
        """SELECT cb.id::text AS placement_id,
                  cb.destination_parent_id::text AS parent_id,
                  COALESCE(cb.destination_section, '') AS section,
                  COALESCE(NULLIF(concat_ws(' · ', ci.title, ci.organization), ''), ci.name, ei.institution, '') AS parent_label,
                  COALESCE(cb.wording_snapshot, v.body, '') AS body,
                  (ROW_NUMBER() OVER (
                     PARTITION BY cb.destination_parent_id
                     ORDER BY cb.sort_order, cb.id
                  ) - 1)::int AS line_index
           FROM composition_bullets cb
           JOIN bullets b ON b.id = cb.bullet_id AND b.user_id = %s
           LEFT JOIN bullet_variants v ON v.id = cb.variant_id
           LEFT JOIN content_items ci ON ci.id = cb.destination_parent_id
           LEFT JOIN education_items ei ON ei.id = cb.destination_parent_id
           JOIN composition_items i ON i.composition_id = cb.composition_id
                AND i.section = cb.destination_section AND i.item_id = cb.destination_parent_id
           WHERE cb.composition_id = %s
           ORDER BY cb.destination_section, cb.destination_parent_id, cb.sort_order, cb.id""",
        (user_id, composition_id),
    )
    for row in bullets:
        row["line_id"] = f"{row['parent_id']}-bullet-{row['line_index']}"
    entries = await _many(
        conn,
        """SELECT i.item_id::text AS id,
                  i.section,
                  COALESCE(NULLIF(concat_ws(' · ', ci.title, ci.organization), ''), ci.name, '') AS label
           FROM composition_items i
           JOIN content_items ci ON ci.id = i.item_id AND ci.user_id = %s
           WHERE i.composition_id = %s AND i.section = ANY(%s)
           ORDER BY i.section, i.sort_order, i.id""",
        (user_id, composition_id, list(CONDENSE_ENTRY_SECTIONS)),
    )
    return {
        "description": description,
        "bullets": bullets,
        "entries": entries,
        "revision": int(composition.get("revision") or 0),
    }, None


async def load_pick_inputs(conn, user_id, composition_id: UUID, job_id: UUID, placement_ids: list[UUID] | None = None):
    """Placed bullets (or the listed ones) with their parent label, and the active library
    bullets of those parents. The client never supplies wording."""
    composition = await load_composition(conn, user_id, composition_id, include_archived=False)
    if not composition:
        return None, "resume"
    job = await get_job_description(conn, user_id, job_id)
    if not job:
        return None, "job"
    wanted = [str(item) for item in placement_ids or []]
    placements = await _many(
        conn,
        """SELECT cb.id::text AS placement_id,
                  cb.bullet_id::text AS bullet_id,
                  cb.variant_id::text AS variant_id,
                  COALESCE(b.parent_id, b.education_item_id)::text AS parent_id,
                  COALESCE(cb.destination_section, '') AS section,
                  COALESCE(NULLIF(concat_ws(' · ', ci.title, ci.organization), ''), ci.name, ei.institution, '') AS parent_label,
                  COALESCE(cb.wording_snapshot, v.body, '') AS body,
                  COALESCE(v.name, '') AS variant_name
           FROM composition_bullets cb
           JOIN bullets b ON b.id = cb.bullet_id AND b.user_id = %s
           LEFT JOIN bullet_variants v ON v.id = cb.variant_id
           LEFT JOIN content_items ci ON ci.id = b.parent_id
           LEFT JOIN education_items ei ON ei.id = b.education_item_id
           WHERE cb.composition_id = %s
             AND COALESCE(b.parent_id, b.education_item_id) IS NOT NULL
             AND (cardinality(%s::uuid[]) = 0 OR cb.id = ANY(%s::uuid[]))
           ORDER BY cb.destination_section, cb.destination_parent_id, cb.sort_order, cb.id""",
        (user_id, composition_id, wanted, wanted),
    )
    if wanted and not placements:
        return None, "placement"
    parents = sorted({row["parent_id"] for row in placements})
    library = await _many(
        conn,
        """SELECT b.id::text AS bullet_id,
                  v.id::text AS variant_id,
                  COALESCE(b.parent_id, b.education_item_id)::text AS parent_id,
                  v.name,
                  v.body
           FROM bullets b
           JOIN bullet_variants v ON v.bullet_id = b.id AND v.user_id = b.user_id
           WHERE b.user_id = %s
             AND b.archived_at IS NULL
             AND v.archived_at IS NULL
             AND COALESCE(b.parent_id, b.education_item_id) = ANY(%s::uuid[])
           ORDER BY b.sort_order, v.sort_order, v.id""",
        (user_id, parents),
    )
    # The whole-resume review also needs every placed bullet id, not only the listed ones.
    if wanted:
        placed = await _many(
            conn,
            "SELECT bullet_id::text AS bullet_id FROM composition_bullets WHERE composition_id = %s",
            (composition_id,),
        )
    else:
        placed = placements
    return {
        "description": job["body"] or "",
        "placements": placements,
        "library": library,
        "placed_bullet_ids": [row["bullet_id"] for row in placed],
        "revision": int(composition.get("revision") or 0),
    }, None


async def load_chat_inputs(conn, user_id, composition_id: UUID, job_id: UUID | None):
    """The resume, its placed bullets, the user's active library bullets and, when one is
    chosen, the selected job. No other job is read."""
    if job_id:
        inputs, error = await load_ai_review_inputs(conn, user_id, job_id, composition_id)
        if error:
            return None, error
    else:
        composition = await load_composition(conn, user_id, composition_id, include_archived=False)
        if not composition:
            return None, "resume"
        payload = composition["render_payload"] or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        inputs = {
            "description": "",
            "resume": payload,
            "bullets": await _placed_bullets(conn, user_id, composition_id),
            "review": {},
            "revision": int(composition.get("revision") or 0),
            "job": None,
            "composition": composition,
        }
    inputs["library"] = await _many(
        conn,
        """SELECT b.id::text AS bullet_id,
                  v.id::text AS variant_id,
                  COALESCE(b.parent_id, b.education_item_id)::text AS parent_id,
                  COALESCE(NULLIF(concat_ws(' · ', ci.title, ci.organization), ''), ci.name, ei.institution, '') AS parent_label,
                  v.body
           FROM bullets b
           JOIN bullet_variants v ON v.bullet_id = b.id AND v.user_id = b.user_id
           LEFT JOIN content_items ci ON ci.id = b.parent_id
           LEFT JOIN education_items ei ON ei.id = b.education_item_id
           WHERE b.user_id = %s
             AND b.archived_at IS NULL
             AND v.archived_at IS NULL
             AND COALESCE(b.parent_id, b.education_item_id) IS NOT NULL
             AND NOT EXISTS (
               SELECT 1 FROM composition_bullets cb WHERE cb.composition_id = %s AND cb.variant_id = v.id
             )
           ORDER BY COALESCE(b.parent_id, b.education_item_id), b.sort_order, v.sort_order, v.id""",
        (user_id, composition_id),
    )
    return inputs, None
