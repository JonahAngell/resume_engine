



import json
from uuid import UUID

from psycopg.rows import dict_row

from .skill_groups import same_skill


async def _one(conn, query, params=()):
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(query, params)
        return await cursor.fetchone()


async def _many(conn, query, params=()):
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(query, params)
        return await cursor.fetchall()


def _display_date(row: dict) -> str:
    if row.get("display_date"):
        return row["display_date"]
    year, month = row.get("graduation_year"), row.get("graduation_month")
    if not year:
        return row.get("graduation_date") or ""
    if not month:
        return str(year)
    names = [
        "",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    return f"{names[month]} {year}"


def _education_render(row: dict) -> dict:
    degree = row.get("degree_major") or row.get("degree") or ""
    if row.get("degree_type") and degree:
        degree = f"{row['degree_type']}, {degree}"
    elif row.get("degree_type"):
        degree = row["degree_type"]
    institution = row["institution"]
    if row.get("college_school"):
        institution = f"{institution}, {row['college_school']}"
    return {
        "id": str(row["id"]) if row.get("id") else None,
        "institution": institution,
        "location": row.get("location") or "",
        "degree": degree,
        "graduation_date": row.get("display_date") or row.get("graduation_date") or "",
        "graduation_year": row.get("graduation_year"),
        "graduation_month": row.get("graduation_month"),
        "display_date": row.get("display_date") or "",
        "bullets": [],
    }


async def _apply_resume_placements(conn, user_id, composition_id, resume):
    from .phase2j_repository import apply_placements

    return await apply_placements(conn, user_id, composition_id, resume)


async def _save_library_refresh(conn, user_id, composition_id, payload, source):
    row = await _one(
        conn,
        "UPDATE resume_compositions SET render_payload=%s::jsonb,revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s RETURNING revision",
        (json.dumps(payload), composition_id, user_id),
    )
    if row:
        await conn.execute(
            "INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,%s,%s::jsonb)",
            (
                composition_id,
                user_id,
                row["revision"],
                source,
                json.dumps({"resume": payload}),
            ),
        )


async def ensure_user(conn, user):
    # Read first so an unchanged user costs no write; this runs on every request.
    row = await _one(
        conn,
        "SELECT id,external_id,username,display_name,email FROM app_users WHERE external_id=%s",
        (user.external_id,),
    )
    if row and (row["username"], row["display_name"], row["email"]) == (
        user.username,
        user.display_name,
        user.email,
    ):
        return row
    return await _one(
        conn,
        "INSERT INTO app_users(external_id,username,display_name,email) VALUES(%s,%s,%s,%s) ON CONFLICT(external_id) DO UPDATE SET username=excluded.username,display_name=excluded.display_name,email=excluded.email,updated_at=now() RETURNING id,external_id,username,display_name,email",
        (user.external_id, user.username, user.display_name, user.email),
    )


def _group_by(rows, key, keep_key=False):
    """Split rows (already ordered) into lists keyed by `key`, keeping their order."""
    grouped: dict = {}
    for row in rows:
        parent = row[key] if keep_key else row.pop(key)
        grouped.setdefault(parent, []).append(row)
    return grouped


async def fetch_library(conn, user_id):
    profiles = await _many(
        conn,
        "SELECT id,label,name,phone,email,linkedin_label,linkedin_url,sort_order,archived_at,created_at,updated_at FROM profiles WHERE user_id=%s ORDER BY sort_order,id",
        (user_id,),
    )
    profile_variants = await _many(
        conn,
        """SELECT id,profile_id,name,display_name,phone,email,linkedin_label,linkedin_url,is_default,archived_at
           FROM profile_field_variants WHERE user_id=%s ORDER BY sort_order,id""",
        (user_id,),
    )
    variants_by_profile: dict = {}
    for variant in profile_variants:
        variants_by_profile.setdefault(variant["profile_id"], []).append(variant)
    for profile in profiles:
        profile["field_variants"] = variants_by_profile.get(profile["id"], [])
    summaries = await _many(
        conn,
        "SELECT id,name,body,tags,sort_order,archived_at,created_at,updated_at FROM summary_variants WHERE user_id=%s ORDER BY sort_order,id",
        (user_id,),
    )
    education = await _many(
        conn,
        "SELECT id,institution,college_school,location,degree_type,degree_major,degree,graduation_year,graduation_month,display_date,graduation_date,sort_order,archived_at,created_at,updated_at FROM education_items WHERE user_id=%s ORDER BY sort_order,id",
        (user_id,),
    )
    education_variants = await _many(
        conn,
        """SELECT id,education_item_id,name,institution,college_school,location,degree_type,degree_major,degree,
                  graduation_year,graduation_month,display_date,graduation_date,is_default,archived_at
           FROM education_item_variants WHERE user_id=%s ORDER BY sort_order,id""",
        (user_id,),
    )
    education_variants_by_item = _group_by(education_variants, "education_item_id", keep_key=True)
    education_bullets = _group_by(
        await _many(
            conn,
            "SELECT b.education_item_id,b.id,b.sort_order,b.archived_at,v.id variant_id,v.name variant_name,v.body,v.is_default,v.sort_order variant_sort_order,v.archived_at variant_archived_at FROM bullets b LEFT JOIN bullet_variants v ON v.bullet_id=b.id WHERE b.user_id=%s AND b.education_item_id=ANY(%s) ORDER BY b.sort_order,v.sort_order,v.id",
            (user_id, [item["id"] for item in education]),
        ),
        "education_item_id",
    )
    for item in education:
        item["field_variants"] = education_variants_by_item.get(item["id"], [])
        item["bullets"] = education_bullets.get(item["id"], [])
    groups = await _many(
        conn,
        "SELECT id,name,sort_order,archived_at,created_at,updated_at FROM tool_groups WHERE user_id=%s ORDER BY sort_order,id",
        (user_id,),
    )
    tools_by_group = _group_by(
        await _many(
            conn,
            "SELECT group_id,id,name,sort_order,archived_at,created_at,updated_at FROM tools WHERE user_id=%s AND group_id=ANY(%s) ORDER BY sort_order,id",
            (user_id, [group["id"] for group in groups]),
        ),
        "group_id",
    )
    for group in groups:
        group["items"] = tools_by_group.get(group["id"], [])

    content_variants = await _many(
        conn,
        """SELECT id,content_item_id,name,item_name,subtitle,organization,location,title,date_label,
                  start_year,start_month,end_year,end_month,is_current,is_default,archived_at
           FROM content_item_variants WHERE user_id=%s ORDER BY sort_order,id""",
        (user_id,),
    )

    content_variants_by_item = _group_by(content_variants, "content_item_id", keep_key=True)

    async def content(kind):
        rows = await _many(
            conn,
            "SELECT id,name,subtitle,organization,location,title,date_label,start_year,start_month,end_year,end_month,is_current,tags,sort_order,archived_at,created_at,updated_at FROM content_items WHERE user_id=%s AND kind=%s ORDER BY sort_order,id",
            (user_id, kind),
        )
        bullets = _group_by(
            await _many(
                conn,
                "SELECT b.id,b.parent_id,b.sort_order,b.archived_at,v.id variant_id,v.name variant_name,v.body,v.is_default,v.sort_order variant_sort_order,v.archived_at variant_archived_at,v.updated_at variant_updated_at FROM bullets b LEFT JOIN bullet_variants v ON v.bullet_id=b.id WHERE b.user_id=%s AND b.parent_id=ANY(%s) ORDER BY b.sort_order,v.sort_order,v.id",
                (user_id, [row["id"] for row in rows]),
            ),
            "parent_id",
            keep_key=True,
        )
        for row in rows:
            row["field_variants"] = content_variants_by_item.get(row["id"], [])
            row["bullets"] = bullets.get(row["id"], [])
        return rows

    custom = await _many(
        conn,
        "SELECT id,title,layout,sort_order,archived_at,created_at,updated_at FROM custom_sections WHERE user_id=%s ORDER BY sort_order,id",
        (user_id,),
    )
    entries_by_section = _group_by(
        await _many(
            conn,
            "SELECT section_id,id,primary_text,secondary_text,location,date_label,start_year,start_month,end_year,end_month,is_current,sort_order,archived_at FROM custom_section_entries WHERE user_id=%s AND section_id=ANY(%s) ORDER BY sort_order,id",
            (user_id, [section["id"] for section in custom]),
        ),
        "section_id",
    )
    for section in custom:
        section["entries"] = entries_by_section.get(section["id"], [])
    interests = await _many(
        conn,
        "SELECT id,body,sort_order,archived_at,created_at,updated_at FROM interests WHERE user_id=%s ORDER BY sort_order,id",
        (user_id,),
    )
    compositions = await _many(
        conn,
        "SELECT id,name,description,display_title,target_company,target_role,job_description_id,preferred_page_length,date_format,template_style,skill_row_max,section_sort_modes,profile_id,is_starter,is_default_starter,archived_at,created_at,updated_at,autosaved_at,revision FROM resume_compositions WHERE user_id=%s AND NOT is_starter ORDER BY updated_at DESC,id",
        (user_id,),
    )
    composition_bullets = await _many(
        conn,
        "SELECT cb.composition_id,cb.bullet_id,cb.variant_id FROM composition_bullets cb JOIN resume_compositions c ON c.id=cb.composition_id WHERE c.user_id=%s",
        (user_id,),
    )
    composition_items = await _many(
        conn,
        "SELECT i.composition_id,i.section,i.item_id FROM composition_items i JOIN resume_compositions c ON c.id=i.composition_id WHERE c.user_id=%s",
        (user_id,),
    )
    composition_custom_sections = await _many(
        conn,
        "SELECT s.composition_id,s.section_id FROM composition_custom_sections s JOIN resume_compositions c ON c.id=s.composition_id WHERE c.user_id=%s",
        (user_id,),
    )
    from .default_sets import list_members, list_sets

    return {
        "default_sets": await list_sets(conn, user_id),
        "default_set_members": await list_members(conn, user_id),
        "profiles": profiles,
        "summary_variants": summaries,
        "education": education,
        "tool_groups": groups,
        "projects": await content("project"),
        "employment": await content("employment"),
        "leadership": await content("leadership"),
        "interests": interests,
        "custom_sections": custom,
        "compositions": compositions,
        "composition_bullets": composition_bullets,
        "composition_items": composition_items,
        "composition_custom_sections": composition_custom_sections,
    }


async def load_composition(conn, user_id, composition_id, include_archived=False):
    return await _one(
        conn,
        "SELECT id,name,description,display_title,target_company,target_role,job_description_id,preferred_page_length,date_format,template_style,skill_row_max,section_sort_modes,summary_variant_id,profile_id,profile_variant_id,is_starter,is_default_starter,revision,render_payload,interest_layout,section_order,archived_at,created_at,updated_at,autosaved_at FROM resume_compositions WHERE id=%s AND user_id=%s"
        + ("" if include_archived else " AND archived_at IS NULL"),
        (composition_id, user_id),
    )


_PROFILE_FIELDS = ("name", "phone", "email", "linkedin_label", "linkedin_url")
_PROFILE_ROW = "id,label,name,phone,email,linkedin_label,linkedin_url,sort_order,archived_at,created_at,updated_at"


def _profile_header(row):
    return {key: row.get(key) or "" for key in _PROFILE_FIELDS}


async def _profile_label_taken(conn, user_id, label, except_id=None):
    if except_id:
        row = await _one(
            conn,
            "SELECT id FROM profiles WHERE user_id=%s AND label=%s AND id<>%s",
            (user_id, label, except_id),
        )
    else:
        row = await _one(
            conn,
            "SELECT id FROM profiles WHERE user_id=%s AND label=%s",
            (user_id, label),
        )
    return row is not None


async def _refresh_profile_headers(conn, user_id, profile_id, header):
    compositions = await _many(
        conn,
        "SELECT id,render_payload,profile_variant_id FROM resume_compositions WHERE user_id=%s AND profile_id=%s FOR UPDATE",
        (user_id, profile_id),
    )
    for composition in compositions:
        resume = composition["render_payload"]
        variant_id = composition.get("profile_variant_id")
        if variant_id:
            variant = await _one(
                conn,
                "SELECT display_name AS name,phone,email,linkedin_label,linkedin_url FROM profile_field_variants WHERE id=%s",
                (variant_id,),
            )
            resume["header"] = _profile_header(variant) if variant else header
        else:
            resume["header"] = header
        await _save_library_refresh(
            conn, user_id, composition["id"], resume, "profile-library-update"
        )


async def create_profile(conn, user_id, payload):
    label = payload.label.strip()
    async with conn.transaction():
        if await _profile_label_taken(conn, user_id, label):
            return None, "duplicate"
        row = await _one(
            conn,
            f"INSERT INTO profiles(user_id,label,name,phone,email,linkedin_label,linkedin_url,sort_order) VALUES(%s,%s,%s,%s,%s,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM profiles WHERE user_id=%s)) RETURNING {_PROFILE_ROW}",
            (
                user_id,
                label,
                payload.name.strip(),
                payload.phone.strip(),
                payload.email,
                payload.linkedin_label.strip(),
                payload.linkedin_url,
                user_id,
            ),
        )
        return row, None


async def update_profile(conn, user_id, resource_id, payload):
    label = payload.label.strip()
    async with conn.transaction():
        if await _profile_label_taken(conn, user_id, label, resource_id):
            return None, "duplicate"
        row = await _one(
            conn,
            f"UPDATE profiles SET label=%s,name=%s,phone=%s,email=%s,linkedin_label=%s,linkedin_url=%s,updated_at=now() WHERE id=%s AND user_id=%s RETURNING {_PROFILE_ROW}",
            (
                label,
                payload.name.strip(),
                payload.phone.strip(),
                payload.email,
                payload.linkedin_label.strip(),
                payload.linkedin_url,
                resource_id,
                user_id,
            ),
        )
        if row:
            await _refresh_profile_headers(conn, user_id, resource_id, _profile_header(row))
        return row, None if row else "missing"


async def duplicate_profile(conn, user_id, resource_id, label):
    label = label.strip()
    async with conn.transaction():
        source = await _one(
            conn,
            f"SELECT {_PROFILE_ROW} FROM profiles WHERE id=%s AND user_id=%s",
            (resource_id, user_id),
        )
        if not source:
            return None, "missing"
        if await _profile_label_taken(conn, user_id, label):
            return None, "duplicate"
        row = await _one(
            conn,
            f"INSERT INTO profiles(user_id,label,name,phone,email,linkedin_label,linkedin_url,sort_order) VALUES(%s,%s,%s,%s,%s,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM profiles WHERE user_id=%s)) RETURNING {_PROFILE_ROW}",
            (
                user_id,
                label,
                source["name"],
                source["phone"],
                source["email"],
                source["linkedin_label"],
                source["linkedin_url"],
                user_id,
            ),
        )
        return row, None


async def select_profile(conn, user_id, composition_id, expected_revision, profile_id):
    async with conn.transaction():
        profile = await _one(
            conn,
            f"SELECT {_PROFILE_ROW} FROM profiles WHERE id=%s AND user_id=%s AND archived_at IS NULL",
            (profile_id, user_id),
        )
        if not profile:
            return None, "missing"
        row = await _one(
            conn,
            "UPDATE resume_compositions SET profile_id=%s,render_payload=jsonb_set(render_payload,'{header}',%s::jsonb),revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s RETURNING *",
            (
                profile_id,
                json.dumps(_profile_header(profile)),
                composition_id,
                user_id,
                expected_revision,
            ),
        )
        if row:
            await conn.execute(
                "INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,'profile-selection',%s::jsonb)",
                (
                    composition_id,
                    user_id,
                    row["revision"],
                    json.dumps({"resume": row["render_payload"]}),
                ),
            )
            return row, None
        exists = await _one(
            conn,
            "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",
            (composition_id, user_id),
        )
        return None, "stale" if exists else "missing"


async def create_summary(conn, user_id, payload):
    return await _one(
        conn,
        "INSERT INTO summary_variants(user_id,name,body,sort_order) VALUES(%s,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM summary_variants WHERE user_id=%s)) RETURNING *",
        (user_id, payload.name.strip(), payload.body.strip(), user_id),
    )


async def update_summary(conn, user_id, resource_id, payload):
    async with conn.transaction():
        row = await _one(
            conn,
            "UPDATE summary_variants SET name=%s,body=%s,updated_at=now() WHERE id=%s AND user_id=%s RETURNING *",
            (payload.name.strip(), payload.body.strip(), resource_id, user_id),
        )
        if row:
            compositions = await _many(
                conn,
                "SELECT id,render_payload FROM resume_compositions WHERE user_id=%s AND summary_variant_id=%s FOR UPDATE",
                (user_id, resource_id),
            )
            for composition in compositions:
                resume = composition["render_payload"]
                resume["summary"] = row["body"]
                await _save_library_refresh(
                    conn, user_id, composition["id"], resume, "summary-library-update"
                )
        return row


async def duplicate_summary(conn, user_id, resource_id):
    return await _one(
        conn,
        "INSERT INTO summary_variants(user_id,name,body,tags,sort_order) SELECT user_id,name || ' Copy',body,tags,(SELECT COALESCE(max(sort_order)+1,0) FROM summary_variants WHERE user_id=%s) FROM summary_variants WHERE id=%s AND user_id=%s RETURNING *",
        (user_id, resource_id, user_id),
    )


async def create_education(conn, user_id, payload):
    legacy_degree = payload.degree_major.strip()
    legacy_date = payload.display_date.strip() or (
        str(payload.graduation_year) if payload.graduation_year else ""
    )
    return await _one(
        conn,
        "INSERT INTO education_items(user_id,institution,college_school,location,degree_type,degree_major,degree,graduation_year,graduation_month,display_date,graduation_date,sort_order) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM education_items WHERE user_id=%s)) RETURNING *",
        (
            user_id,
            payload.institution.strip(),
            payload.college_school.strip() or None,
            payload.location.strip(),
            payload.degree_type.strip() or None,
            payload.degree_major.strip() or None,
            legacy_degree,
            payload.graduation_year,
            payload.graduation_month,
            payload.display_date.strip() or None,
            legacy_date,
            user_id,
        ),
    )


async def update_education(conn, user_id, resource_id, payload):
    legacy_degree = payload.degree_major.strip()
    legacy_date = payload.display_date.strip() or (
        str(payload.graduation_year) if payload.graduation_year else ""
    )
    async with conn.transaction():
        row = await _one(
            conn,
            "UPDATE education_items SET institution=%s,college_school=%s,location=%s,degree_type=%s,degree_major=%s,degree=%s,graduation_year=%s,graduation_month=%s,display_date=%s,graduation_date=%s,updated_at=now() WHERE id=%s AND user_id=%s RETURNING *",
            (
                payload.institution.strip(),
                payload.college_school.strip() or None,
                payload.location.strip(),
                payload.degree_type.strip() or None,
                payload.degree_major.strip() or None,
                legacy_degree,
                payload.graduation_year,
                payload.graduation_month,
                payload.display_date.strip() or None,
                legacy_date,
                resource_id,
                user_id,
            ),
        )
        if row:
            comps = await _many(
                conn,
                "SELECT c.id,c.render_payload FROM resume_compositions c JOIN composition_items i ON i.composition_id=c.id WHERE c.user_id=%s AND i.section='education' AND i.item_id=%s",
                (user_id, resource_id),
            )
            for comp in comps:
                items = list(comp["render_payload"].get("education", []))
                selected = await _many(
                    conn,
                    """SELECT e.*, v.institution v_institution, v.college_school v_college, v.location v_location,
                              v.degree_type v_degree_type, v.degree_major v_degree_major, v.degree v_degree,
                              v.graduation_year v_year, v.graduation_month v_month, v.display_date v_display,
                              v.graduation_date v_graduation
                       FROM composition_items i
                       JOIN education_items e ON e.id=i.item_id
                       LEFT JOIN education_item_variants v ON v.id=i.variant_id
                       WHERE i.composition_id=%s AND i.section='education'
                       ORDER BY i.sort_order""",
                    (comp["id"],),
                )
                rendered = []
                for item in selected:
                    if item.get("v_institution") is not None:
                        item = {
                            **item,
                            "institution": item["v_institution"],
                            "college_school": item["v_college"],
                            "location": item["v_location"] or "",
                            "degree_type": item["v_degree_type"],
                            "degree_major": item["v_degree_major"],
                            "degree": item["v_degree"] or "",
                            "graduation_year": item["v_year"],
                            "graduation_month": item["v_month"],
                            "display_date": item["v_display"],
                            "graduation_date": item["v_graduation"] or "",
                        }
                    rendered.append(_education_render(item))
                items = rendered
                resume = comp["render_payload"]
                resume["education"] = items
                resume = await _apply_resume_placements(
                    conn, user_id, comp["id"], resume
                )
                await _save_library_refresh(
                    conn, user_id, comp["id"], resume, "education-library-update"
                )
        return row


async def create_interest(conn, user_id, payload):
    return await _one(
        conn,
        "INSERT INTO interests(user_id,body,sort_order) VALUES(%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM interests WHERE user_id=%s)) RETURNING *",
        (user_id, payload.body.strip(), user_id),
    )


async def update_interest(conn, user_id, resource_id, payload):
    async with conn.transaction():
        row = await _one(
            conn,
            "UPDATE interests SET body=%s,updated_at=now() WHERE id=%s AND user_id=%s RETURNING *",
            (payload.body.strip(), resource_id, user_id),
        )
        if row:
            await _refresh_interest_compositions(conn, user_id, resource_id)
        return row


async def _refresh_interest_compositions(conn, user_id, interest_id):
    composition_ids = await _many(
        conn,
        "SELECT DISTINCT c.id FROM resume_compositions c JOIN composition_items i ON i.composition_id=c.id WHERE c.user_id=%s AND i.section='personal_interests' AND i.item_id=%s",
        (user_id, interest_id),
    )
    for item in composition_ids:
        selected = await _many(
            conn,
            "SELECT x.body FROM composition_items i JOIN interests x ON x.id=i.item_id WHERE i.composition_id=%s AND i.section='personal_interests' ORDER BY i.sort_order",
            (item["id"],),
        )
        composition = await _one(
            conn,
            "SELECT render_payload FROM resume_compositions WHERE id=%s AND user_id=%s FOR UPDATE",
            (item["id"], user_id),
        )
        resume = composition["render_payload"]
        resume["personal_interests"] = [x["body"] for x in selected]
        await _save_library_refresh(
            conn, user_id, item["id"], resume, "interest-library-update"
        )


async def reorder(conn, user_id, kind, ids):
    table = {
        "summaries": "summary_variants",
        "education": "education_items",
        "interests": "interests",
        "tool-groups": "tool_groups",
    }.get(kind)
    if not table:
        return False
    async with conn.transaction():
        owned = await _many(
            conn,
            f"SELECT id FROM {table} WHERE user_id=%s AND id=ANY(%s)",
            (user_id, ids),
        )
        if {x["id"] for x in owned} != set(ids):
            return False
        for index, resource_id in enumerate(ids):
            await conn.execute(
                f"UPDATE {table} SET sort_order=%s,updated_at=now() WHERE id=%s AND user_id=%s",
                (index, resource_id, user_id),
            )
    return True


async def select_summary(conn, user_id, composition_id, expected_revision, summary_id):
    async with conn.transaction():
        body = ""
        if summary_id:
            summary = await _one(
                conn,
                "SELECT body FROM summary_variants WHERE id=%s AND user_id=%s AND archived_at IS NULL",
                (summary_id, user_id),
            )
            if not summary:
                return None, "missing"
            body = summary["body"]
        row = await _one(
            conn,
            "UPDATE resume_compositions SET summary_variant_id=%s,render_payload=jsonb_set(render_payload,'{summary}',to_jsonb(%s::text)),revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s RETURNING *",
            (summary_id, body, composition_id, user_id, expected_revision),
        )
        if row:
            await conn.execute(
                "INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,'summary-selection',%s::jsonb)",
                (
                    composition_id,
                    user_id,
                    row["revision"],
                    json.dumps({"resume": row["render_payload"]}),
                ),
            )
            return row, None
        exists = await _one(
            conn,
            "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",
            (composition_id, user_id),
        )
        return None, "stale" if exists else "missing"


async def select_interest(
    conn, user_id, composition_id, expected_revision, interest_id, included
):
    async with conn.transaction():
        interest = await _one(
            conn,
            "SELECT id FROM interests WHERE id=%s AND user_id=%s AND (archived_at IS NULL OR EXISTS(SELECT 1 FROM composition_items WHERE composition_id=%s AND section='personal_interests' AND item_id=%s))",
            (interest_id, user_id, composition_id, interest_id),
        )
        if not interest:
            return None, "missing"
        locked = await _one(
            conn,
            "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s FOR UPDATE",
            (composition_id, user_id, expected_revision),
        )
        if not locked:
            exists = await _one(
                conn,
                "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",
                (composition_id, user_id),
            )
            return None, "stale" if exists else "missing"
        if included:
            await conn.execute(
                "INSERT INTO composition_items(composition_id,section,item_id,sort_order) VALUES(%s,'personal_interests',%s,(SELECT COALESCE(max(sort_order)+1,0) FROM composition_items WHERE composition_id=%s AND section='personal_interests')) ON CONFLICT DO NOTHING",
                (composition_id, interest_id, composition_id),
            )
        else:
            await conn.execute(
                "DELETE FROM composition_items WHERE composition_id=%s AND section='personal_interests' AND item_id=%s",
                (composition_id, interest_id),
            )
        selected = await _many(
            conn,
            "SELECT x.body FROM composition_items i JOIN interests x ON x.id=i.item_id WHERE i.composition_id=%s AND i.section='personal_interests' ORDER BY i.sort_order",
            (composition_id,),
        )
        row = await _one(
            conn,
            "UPDATE resume_compositions SET render_payload=jsonb_set(render_payload,'{personal_interests}',%s::jsonb),revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s RETURNING *",
            (json.dumps([x["body"] for x in selected]), composition_id, user_id),
        )
        await conn.execute(
            "INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,'interest-selection',%s::jsonb)",
            (
                composition_id,
                user_id,
                row["revision"],
                json.dumps({"resume": row["render_payload"]}),
            ),
        )
        return row, None


async def search(conn, user_id, query, status, limit, offset):
    term = query.strip()
    like = f"%{term}%"
    rows = await _many(conn, """
    WITH results AS (
      SELECT s.id,'summary' type,s.name label,NULL::text context,(s.archived_at IS NOT NULL) archived,s.tags
      FROM summary_variants s WHERE s.user_id=%s AND (s.name||' '||s.body ILIKE %s OR EXISTS(SELECT 1 FROM unnest(s.tags) tag WHERE tag ILIKE %s))
      UNION ALL
      SELECT p.id,'profile',p.label,concat_ws(' · ',p.name,p.email),(p.archived_at IS NOT NULL),'{}'::text[]
      FROM profiles p WHERE p.user_id=%s AND concat_ws(' ',p.label,p.name,p.phone,p.email,p.linkedin_label,p.linkedin_url) ILIKE %s
      UNION ALL
      SELECT e.id,'education',e.institution,concat_ws(' · ',e.college_school,e.degree_type,e.degree_major,e.location,e.display_date),(e.archived_at IS NOT NULL),'{}'::text[]
      FROM education_items e WHERE e.user_id=%s AND concat_ws(' ',e.institution,e.college_school,e.degree_type,e.degree_major,e.degree,e.location,e.display_date,e.graduation_date) ILIKE %s
      UNION ALL
      SELECT i.id,'interest',i.body,NULL,(i.archived_at IS NOT NULL),'{}'::text[] FROM interests i WHERE i.user_id=%s AND i.body ILIKE %s
      UNION ALL
      SELECT c.id,'composition',c.name,c.description,(c.archived_at IS NOT NULL),c.tags FROM resume_compositions c WHERE c.user_id=%s AND (concat_ws(' ',c.name,c.description,c.display_title,c.target_company,c.target_role) ILIKE %s OR EXISTS(SELECT 1 FROM unnest(c.tags) tag WHERE tag ILIKE %s))
      UNION ALL
      SELECT g.id,'tool_group',g.name,NULL,(g.archived_at IS NOT NULL),'{}'::text[] FROM tool_groups g WHERE g.user_id=%s AND g.name ILIKE %s
      UNION ALL
      SELECT t.id,'tool',t.name,g.name,(t.archived_at IS NOT NULL OR g.archived_at IS NOT NULL),'{}'::text[] FROM tools t JOIN tool_groups g ON g.id=t.group_id AND g.user_id=t.user_id WHERE t.user_id=%s AND (t.name ILIKE %s OR g.name ILIKE %s)
      UNION ALL
      SELECT x.id,x.kind,COALESCE(x.name,x.organization),concat_ws(' · ',x.title,x.subtitle,x.location,x.date_label),(x.archived_at IS NOT NULL),x.tags FROM content_items x WHERE x.user_id=%s AND (concat_ws(' ',x.name,x.organization,x.title,x.subtitle,x.location,x.date_label) ILIKE %s OR EXISTS(SELECT 1 FROM unnest(x.tags) tag WHERE tag ILIKE %s))
      UNION ALL
      SELECT v.id,'wording_variant',v.name,concat_ws(' · ',v.body,COALESCE(x.name,x.organization),x.title),(v.archived_at IS NOT NULL OR b.archived_at IS NOT NULL OR x.archived_at IS NOT NULL),'{}'::text[] FROM bullet_variants v JOIN bullets b ON b.id=v.bullet_id AND b.user_id=v.user_id JOIN content_items x ON x.id=b.parent_id AND x.user_id=b.user_id WHERE v.user_id=%s AND (v.name ILIKE %s OR v.body ILIKE %s)
      UNION ALL
      SELECT cs.id,'custom_section',cs.title,cs.layout,(cs.archived_at IS NOT NULL),'{}'::text[] FROM custom_sections cs WHERE cs.user_id=%s AND cs.title ILIKE %s
      UNION ALL
      SELECT ce.id,'custom_entry',ce.primary_text,concat_ws(' · ',cs.title,ce.secondary_text,ce.location,ce.date_label),(ce.archived_at IS NOT NULL OR cs.archived_at IS NOT NULL),'{}'::text[] FROM custom_section_entries ce JOIN custom_sections cs ON cs.id=ce.section_id AND cs.user_id=ce.user_id WHERE ce.user_id=%s AND concat_ws(' ',ce.primary_text,ce.secondary_text,ce.location,ce.date_label,cs.title) ILIKE %s
    )
    SELECT id,type,label,context,archived,tags FROM results
    WHERE (%s='all' OR (%s='archived' AND archived) OR (%s='active' AND NOT archived))
    ORDER BY lower(label),type,id LIMIT %s OFFSET %s
    """,
    (
        user_id, like, like,
        user_id, like,
        user_id, like,
        user_id, like,
        user_id, like, like,
        user_id, like,
        user_id, like, like,
        user_id, like, like,
        user_id, like, like,
        user_id, like,
        user_id, like,
        status, status, status,
        limit, offset,
    ))
    return rows
async def set_archive(conn, user_id, table, resource_id, archived):
    allowed = {
        "summary_variants",
        "profiles",
        "education_items",
        "tool_groups",
        "tools",
        "content_items",
        "bullets",
        "bullet_variants",
        "interests",
        "custom_sections",
        "custom_section_entries",
        "resume_compositions",
    }
    if table not in allowed:
        return None
    if table == "tools":
        tool = await _one(
            conn,
            "SELECT group_id FROM tools WHERE id=%s AND user_id=%s",
            (resource_id, user_id),
        )
        if not tool:
            return None
        row = await _one(
            conn,
            "UPDATE tools SET archived_at="
            + ("now()" if archived else "NULL")
            + ",updated_at=now() WHERE id=%s AND user_id=%s RETURNING id",
            (resource_id, user_id),
        )
        if row:
            await _refresh_tool_compositions(
                conn,
                user_id,
                tool["group_id"],
                "tool-archive" if archived else "tool-restore",
            )
        return row
    return await _one(
        conn,
        f"UPDATE {table} SET archived_at="
        + ("now()" if archived else "NULL")
        + ",updated_at=now() WHERE id=%s AND user_id=%s RETURNING id",
        (resource_id, user_id),
    )


async def create_tool_group(conn, user_id, payload):
    return await _one(
        conn,
        "INSERT INTO tool_groups(user_id,name,sort_order) VALUES(%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM tool_groups WHERE user_id=%s)) RETURNING *",
        (user_id, payload.name.strip(), user_id),
    )


async def update_tool_group(conn, user_id, rid, payload):
    async with conn.transaction():
        row = await _one(
            conn,
            "UPDATE tool_groups SET name=%s,updated_at=now() WHERE id=%s AND user_id=%s AND archived_at IS NULL RETURNING *",
            (payload.name.strip(), rid, user_id),
        )
        if row:
            await _refresh_tool_compositions(conn, user_id, rid, "tool-group-update")
        return row


async def create_tool(conn, user_id, payload):
    group = await _one(
        conn,
        "SELECT id FROM tool_groups WHERE id=%s AND user_id=%s AND archived_at IS NULL",
        (payload.group_id, user_id),
    )
    if not group:
        return None
    row = await _one(
        conn,
        "INSERT INTO tools(user_id,group_id,name,sort_order) VALUES(%s,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM tools WHERE group_id=%s)) RETURNING *",
        (user_id, payload.group_id, payload.name.strip(), payload.group_id),
    )
    await _refresh_tool_compositions(conn, user_id, payload.group_id, "tool-create")
    return row


async def update_tool(conn, user_id, rid, payload):
    async with conn.transaction():
        prior = await _one(
            conn,
            "SELECT group_id FROM tools WHERE id=%s AND user_id=%s AND archived_at IS NULL",
            (rid, user_id),
        )
        group = await _one(
            conn,
            "SELECT id FROM tool_groups WHERE id=%s AND user_id=%s AND archived_at IS NULL",
            (payload.group_id, user_id),
        )
        if not prior or not group:
            return None
        row = await _one(
            conn,
            "UPDATE tools SET name=%s,group_id=%s,updated_at=now() WHERE id=%s AND user_id=%s RETURNING *",
            (payload.name.strip(), payload.group_id, rid, user_id),
        )
        await _refresh_tool_compositions(
            conn, user_id, prior["group_id"], "tool-update"
        )
        if prior["group_id"] != payload.group_id:
            await _refresh_tool_compositions(
                conn, user_id, payload.group_id, "tool-move"
            )
        return row


async def reorder_tools(conn, user_id, group_id, ids):
    async with conn.transaction():
        group = await _one(
            conn,
            "SELECT id FROM tool_groups WHERE id=%s AND user_id=%s",
            (group_id, user_id),
        )
        owned = await _many(
            conn,
            "SELECT id FROM tools WHERE user_id=%s AND group_id=%s AND id=ANY(%s)",
            (user_id, group_id, ids),
        )
        if not group or {x["id"] for x in owned} != set(ids):
            return False
        for i, rid in enumerate(ids):
            await conn.execute(
                "UPDATE tools SET sort_order=%s,updated_at=now() WHERE id=%s AND user_id=%s AND group_id=%s",
                (i, rid, user_id, group_id),
            )
        await _refresh_tool_compositions(conn, user_id, group_id, "tool-reorder")
    return True


async def move_tool(conn, user_id, rid, group_id):
    async with conn.transaction():
        tool = await _one(
            conn,
            "SELECT group_id FROM tools WHERE id=%s AND user_id=%s AND archived_at IS NULL FOR UPDATE",
            (rid, user_id),
        )
        group = await _one(
            conn,
            "SELECT id FROM tool_groups WHERE id=%s AND user_id=%s AND archived_at IS NULL",
            (group_id, user_id),
        )
        if not tool or not group:
            return None
        await conn.execute(
            "UPDATE tools SET group_id=%s,sort_order=(SELECT COALESCE(max(sort_order)+1,0) FROM tools WHERE group_id=%s),updated_at=now() WHERE id=%s AND user_id=%s",
            (group_id, group_id, rid, user_id),
        )
        await _refresh_tool_compositions(conn, user_id, tool["group_id"], "tool-move")
        await _refresh_tool_compositions(conn, user_id, group_id, "tool-move")
        return {"id": rid}


async def restore_tool(conn, user_id, rid, outcome, group_id=None):
    async with conn.transaction():
        tool = await _one(
            conn,
            "SELECT id,group_id FROM tools WHERE id=%s AND user_id=%s AND archived_at IS NOT NULL FOR UPDATE",
            (rid, user_id),
        )
        if not tool:
            return None, "missing"
        parent = await _one(
            conn,
            "SELECT archived_at FROM tool_groups WHERE id=%s AND user_id=%s",
            (tool["group_id"], user_id),
        )
        if not parent:
            return None, "missing"
        target = tool["group_id"]
        if parent["archived_at"]:
            if outcome == "restore-parent":
                await conn.execute(
                    "UPDATE tool_groups SET archived_at=NULL,updated_at=now() WHERE id=%s AND user_id=%s",
                    (target, user_id),
                )
            elif outcome == "move" and group_id:
                active = await _one(
                    conn,
                    "SELECT id FROM tool_groups WHERE id=%s AND user_id=%s AND archived_at IS NULL",
                    (group_id, user_id),
                )
                if not active:
                    return None, "parent"
                target = group_id
            else:
                return None, "parent"
        await conn.execute(
            "UPDATE tools SET archived_at=NULL,group_id=%s,sort_order=(SELECT COALESCE(max(sort_order)+1,0) FROM tools WHERE group_id=%s),updated_at=now() WHERE id=%s AND user_id=%s",
            (target, target, rid, user_id),
        )
        await _refresh_tool_compositions(conn, user_id, target, "tool-restore")
        return {"id": rid}, None


async def _tool_groups_render(conn, user_id, group_ids, composition_id):
    """Render a composition's tool groups, in the given order, with two queries."""
    group_ids = list(group_ids)
    if not group_ids:
        return []
    groups = await _many(
        conn,
        "SELECT id,name FROM tool_groups WHERE user_id=%s AND id=ANY(%s)",
        (user_id, group_ids),
    )
    names = {str(x["id"]): x["name"] for x in groups}
    tools = await _many(
        conn,
        """SELECT t.id,t.name,t.group_id FROM tools t
           LEFT JOIN composition_tool_order o ON o.tool_id=t.id AND o.composition_id=%s
           WHERE t.user_id=%s AND t.group_id=ANY(%s) AND t.archived_at IS NULL
             AND NOT EXISTS (SELECT 1 FROM composition_hidden_tools h WHERE h.composition_id=%s AND h.tool_id=t.id)
           ORDER BY o.sort_order NULLS LAST, t.sort_order, t.id""",
        (composition_id, user_id, group_ids, composition_id),
    )
    items: dict[str, list[str]] = {}
    for tool in tools:
        items.setdefault(str(tool["group_id"]), []).append(tool["name"])
    return [
        {"name": names[str(gid)], "items": items.get(str(gid), [])} if str(gid) in names else None
        for gid in group_ids
    ]


async def _refresh_tool_compositions(conn, user_id, group_id, source):
    comps = await _many(
        conn,
        "SELECT c.id,c.render_payload FROM resume_compositions c JOIN composition_items i ON i.composition_id=c.id WHERE c.user_id=%s AND i.section='tool_groups' AND i.item_id=%s FOR UPDATE",
        (user_id, group_id),
    )
    for comp in comps:
        selected = await _many(
            conn,
            "SELECT item_id FROM composition_items WHERE composition_id=%s AND section='tool_groups' ORDER BY sort_order,id",
            (comp["id"],),
        )
        resume = comp["render_payload"]
        resume["tool_groups"] = await _tool_groups_render(
            conn, user_id, [x["item_id"] for x in selected], comp["id"]
        )
        await _save_library_refresh(conn, user_id, comp["id"], resume, source)


async def select_tool_group(conn, user_id, cid, expected, group_id, included):
    async with conn.transaction():
        group = await _one(
            conn,
            "SELECT id,archived_at FROM tool_groups WHERE id=%s AND user_id=%s",
            (group_id, user_id),
        )
        if not group or (included and group["archived_at"]):
            return None, "missing"
        locked = await _one(
            conn,
            "SELECT render_payload FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s FOR UPDATE",
            (cid, user_id, expected),
        )
        if not locked:
            return None, (
                "stale"
                if await _one(
                    conn,
                    "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",
                    (cid, user_id),
                )
                else "missing"
            )
        if included:
            await conn.execute(
                "INSERT INTO composition_items(composition_id,section,item_id,sort_order) VALUES(%s,'tool_groups',%s,(SELECT COALESCE(max(sort_order)+1,0) FROM composition_items WHERE composition_id=%s AND section='tool_groups')) ON CONFLICT DO NOTHING",
                (cid, group_id, cid),
            )
        else:
            await conn.execute(
                "DELETE FROM composition_items WHERE composition_id=%s AND section='tool_groups' AND item_id=%s",
                (cid, group_id),
            )
        selected = await _many(
            conn,
            "SELECT item_id FROM composition_items WHERE composition_id=%s AND section='tool_groups' ORDER BY sort_order,id",
            (cid,),
        )
        resume = locked["render_payload"]
        resume["tool_groups"] = await _tool_groups_render(
            conn, user_id, [x["item_id"] for x in selected], cid
        )
        row = await _one(
            conn,
            "UPDATE resume_compositions SET render_payload=%s::jsonb,revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s RETURNING *",
            (json.dumps(resume), cid, user_id),
        )
        await conn.execute(
            "INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,'tool-selection',%s::jsonb)",
            (cid, user_id, row["revision"], json.dumps({"resume": resume})),
        )
        return row, None


async def tool_order(conn, user_id, composition_id):
    exists = await _one(
        conn,
        "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s",
        (composition_id, user_id),
    )
    if not exists:
        return None
    return await _many(
        conn,
        "SELECT tool_id,sort_order FROM composition_tool_order WHERE composition_id=%s ORDER BY sort_order,tool_id",
        (composition_id,),
    )


async def set_tool_order(conn, user_id, cid, expected, group_id, ids):
    async with conn.transaction():
        group = await _one(
            conn,
            "SELECT id FROM tool_groups WHERE id=%s AND user_id=%s AND archived_at IS NULL",
            (group_id, user_id),
        )
        if not group:
            return None, "missing"
        locked = await _one(
            conn,
            "SELECT render_payload FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s FOR UPDATE",
            (cid, user_id, expected),
        )
        if not locked:
            return None, (
                "stale"
                if await _one(
                    conn,
                    "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",
                    (cid, user_id),
                )
                else "missing"
            )
        member = await _one(
            conn,
            "SELECT 1 FROM composition_items WHERE composition_id=%s AND section='tool_groups' AND item_id=%s",
            (cid, group_id),
        )
        active = await _many(
            conn,
            "SELECT id FROM tools WHERE user_id=%s AND group_id=%s AND archived_at IS NULL",
            (user_id, group_id),
        )
        if not member or {str(x["id"]) for x in active} != {str(x) for x in ids}:
            return None, "invalid"
        await conn.execute(
            """DELETE FROM composition_tool_order o USING tools t
               WHERE o.composition_id=%s AND o.tool_id=t.id AND t.group_id=%s""",
            (cid, group_id),
        )
        for index, tool_id in enumerate(ids):
            await conn.execute(
                "INSERT INTO composition_tool_order(composition_id,tool_id,sort_order) VALUES(%s,%s,%s)",
                (cid, tool_id, index),
            )
        selected = await _many(
            conn,
            "SELECT item_id FROM composition_items WHERE composition_id=%s AND section='tool_groups' ORDER BY sort_order,id",
            (cid,),
        )
        resume = locked["render_payload"]
        resume["tool_groups"] = await _tool_groups_render(
            conn, user_id, [x["item_id"] for x in selected], cid
        )
        row = await _one(
            conn,
            "UPDATE resume_compositions SET render_payload=%s::jsonb,revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s RETURNING *",
            (json.dumps(resume), cid, user_id),
        )
        await conn.execute(
            "INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,'tool-order',%s::jsonb)",
            (cid, user_id, row["revision"], json.dumps({"resume": resume})),
        )
        return row, None


async def hidden_tools(conn, user_id, composition_id):
    exists = await _one(
        conn,
        "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s",
        (composition_id, user_id),
    )
    if not exists:
        return None
    return await _many(
        conn,
        "SELECT h.tool_id FROM composition_hidden_tools h WHERE h.composition_id=%s ORDER BY h.tool_id",
        (composition_id,),
    )


async def set_tool_visibility(conn, user_id, cid, expected, tool_id, included):
    async with conn.transaction():
        tool = await _one(
            conn,
            "SELECT id,group_id FROM tools WHERE id=%s AND user_id=%s AND archived_at IS NULL",
            (tool_id, user_id),
        )
        if not tool:
            return None, "missing"
        locked = await _one(
            conn,
            "SELECT render_payload FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s FOR UPDATE",
            (cid, user_id, expected),
        )
        if not locked:
            return None, (
                "stale"
                if await _one(
                    conn,
                    "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",
                    (cid, user_id),
                )
                else "missing"
            )
        member = await _one(
            conn,
            "SELECT 1 FROM composition_items WHERE composition_id=%s AND section='tool_groups' AND item_id=%s",
            (cid, tool["group_id"]),
        )
        if not member:
            return None, "missing"
        if included:
            await conn.execute(
                "DELETE FROM composition_hidden_tools WHERE composition_id=%s AND tool_id=%s",
                (cid, tool_id),
            )
        else:
            await conn.execute(
                "INSERT INTO composition_hidden_tools(composition_id,tool_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                (cid, tool_id),
            )
        selected = await _many(
            conn,
            "SELECT item_id FROM composition_items WHERE composition_id=%s AND section='tool_groups' ORDER BY sort_order,id",
            (cid,),
        )
        resume = locked["render_payload"]
        resume["tool_groups"] = await _tool_groups_render(
            conn, user_id, [x["item_id"] for x in selected], cid
        )
        row = await _one(
            conn,
            "UPDATE resume_compositions SET render_payload=%s::jsonb,revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s RETURNING *",
            (json.dumps(resume), cid, user_id),
        )
        await conn.execute(
            "INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,'tool-visibility',%s::jsonb)",
            (cid, user_id, row["revision"], json.dumps({"resume": resume})),
        )
        return row, None


def _custom_render(section, entries):
    return {
        "id": str(section["id"]),
        "title": section["title"],
        "layout": section["layout"],
        "entries": [
            {
                "id": str(x["id"]),
                "primary_text": x["primary_text"],
                "secondary_text": x.get("secondary_text"),
                "location": x.get("location"),
                "date": x.get("date_label") or "",
                "date_label": x.get("date_label") or "",
                "start_year": x.get("start_year"), "start_month": x.get("start_month"),
                "end_year": x.get("end_year"), "end_month": x.get("end_month"),
                "is_current": x.get("is_current", False),
                "bullets": [],
            }
            for x in entries
            if not x.get("archived_at")
        ],
    }


async def create_custom_section(conn, user_id, payload):
    return await _one(
        conn,
        "INSERT INTO custom_sections(user_id,title,layout,sort_order) VALUES(%s,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM custom_sections WHERE user_id=%s)) RETURNING *",
        (user_id, payload.title.strip(), payload.layout, user_id),
    )


async def update_custom_section(conn, user_id, rid, payload):
    async with conn.transaction():
        row = await _one(
            conn,
            "UPDATE custom_sections SET title=%s,layout=%s,updated_at=now() WHERE id=%s AND user_id=%s AND archived_at IS NULL RETURNING *",
            (payload.title.strip(), payload.layout, rid, user_id),
        )
        if row:
            await _refresh_custom_compositions(
                conn, user_id, rid, "custom-section-update"
            )
        return row


async def create_custom_entry(conn, user_id, payload):
    parent = await _one(
        conn,
        "SELECT id FROM custom_sections WHERE id=%s AND user_id=%s AND archived_at IS NULL",
        (payload.section_id, user_id),
    )
    if not parent:
        return None
    row = await _one(
        conn,
        "INSERT INTO custom_section_entries(user_id,section_id,primary_text,secondary_text,location,date_label,start_year,start_month,end_year,end_month,is_current,sort_order) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM custom_section_entries WHERE section_id=%s)) RETURNING *",
        (
            user_id,
            payload.section_id,
            payload.primary_text.strip(),
            payload.secondary_text.strip() or None,
            payload.location.strip() or None,
            payload.date_label.strip() or None,
            getattr(payload,"start_year",None),getattr(payload,"start_month",None),getattr(payload,"end_year",None),getattr(payload,"end_month",None),getattr(payload,"is_current",False),
            payload.section_id,
        ),
    )
    await _refresh_custom_compositions(
        conn, user_id, payload.section_id, "custom-entry-create"
    )
    return row


async def update_custom_entry(conn, user_id, rid, payload):
    async with conn.transaction():
        chain = await _one(
            conn,
            "SELECT e.section_id FROM custom_section_entries e JOIN custom_sections s ON s.id=e.section_id AND s.user_id=e.user_id WHERE e.id=%s AND e.user_id=%s AND s.id=%s AND s.archived_at IS NULL",
            (rid, user_id, payload.section_id),
        )
        if not chain:
            return None
        row = await _one(
            conn,
            "UPDATE custom_section_entries SET primary_text=%s,secondary_text=%s,location=%s,date_label=%s,start_year=%s,start_month=%s,end_year=%s,end_month=%s,is_current=%s,updated_at=now() WHERE id=%s AND user_id=%s AND section_id=%s RETURNING *",
            (
                payload.primary_text.strip(),
                payload.secondary_text.strip() or None,
                payload.location.strip() or None,
                payload.date_label.strip() or None,
                getattr(payload,"start_year",None),getattr(payload,"start_month",None),getattr(payload,"end_year",None),getattr(payload,"end_month",None),getattr(payload,"is_current",False),
                rid,
                user_id,
                payload.section_id,
            ),
        )
        await _refresh_custom_compositions(
            conn, user_id, payload.section_id, "custom-entry-update"
        )
        return row


async def reorder_custom_entries(conn, user_id, section_id, ids):
    async with conn.transaction():
        parent = await _one(
            conn,
            "SELECT id FROM custom_sections WHERE id=%s AND user_id=%s",
            (section_id, user_id),
        )
        rows = await _many(
            conn,
            "SELECT id FROM custom_section_entries WHERE section_id=%s AND user_id=%s",
            (section_id, user_id),
        )
        if not parent or {x["id"] for x in rows} != set(ids):
            return False
        for i, rid in enumerate(ids):
            await conn.execute(
                "UPDATE custom_section_entries SET sort_order=%s,updated_at=now() WHERE id=%s AND user_id=%s AND section_id=%s",
                (i, rid, user_id, section_id),
            )
        await _refresh_custom_compositions(
            conn, user_id, section_id, "custom-entry-reorder"
        )
        return True


async def set_custom_archive(conn, user_id, kind, rid, archived):
    table = "custom_sections" if kind == "sections" else "custom_section_entries"
    async with conn.transaction():
        if table == "custom_sections":
            row = await _one(
                conn,
                "UPDATE custom_sections SET archived_at="
                + ("now()" if archived else "NULL")
                + ",updated_at=now() WHERE id=%s AND user_id=%s RETURNING id",
                (rid, user_id),
            )
            section_id = rid
        else:
            found = await _one(
                conn,
                "SELECT e.section_id FROM custom_section_entries e JOIN custom_sections s ON s.id=e.section_id AND s.user_id=e.user_id WHERE e.id=%s AND e.user_id=%s",
                (rid, user_id),
            )
            if not found:
                return None
            section_id = found["section_id"]
            row = await _one(
                conn,
                "UPDATE custom_section_entries SET archived_at="
                + ("now()" if archived else "NULL")
                + ",updated_at=now() WHERE id=%s AND user_id=%s RETURNING id",
                (rid, user_id),
            )
        if row:
            await _refresh_custom_compositions(
                conn, user_id, section_id, "custom-archive"
            )
        return row


async def _refresh_custom_compositions(conn, user_id, section_id, source):
    comps = await _many(
        conn,
        "SELECT c.id,c.render_payload FROM resume_compositions c JOIN composition_custom_sections x ON x.composition_id=c.id WHERE c.user_id=%s AND x.section_id=%s FOR UPDATE",
        (user_id, section_id),
    )
    for comp in comps:
        sections = await _many(
            conn,
            "SELECT s.* FROM composition_custom_sections x JOIN custom_sections s ON s.id=x.section_id WHERE x.composition_id=%s AND s.user_id=%s ORDER BY x.sort_order,x.id",
            (comp["id"], user_id),
        )
        rendered = []
        for section in sections:
            entries = await _many(
                conn,
                "SELECT * FROM custom_section_entries WHERE section_id=%s AND user_id=%s ORDER BY sort_order,id",
                (section["id"], user_id),
            )
            rendered.append(_custom_render(section, entries))
        resume = comp["render_payload"]
        resume["custom_sections"] = rendered
        await _save_library_refresh(conn, user_id, comp["id"], resume, source)


async def save_sections_panel(conn, user_id, cid, payload):
    builtin = {
        "summary",
        "education",
        "tools",
        "projects",
        "work_experience",
        "leadership",
        "personal_interests",
    }
    order = payload.section_order

    def visible_key(x):
        return x[7:] if x.startswith("hidden:") else x

    normalized = [visible_key(x) for x in order]
    if len(normalized) != len(set(normalized)) or any(
        x not in builtin and not x.startswith("custom:") for x in normalized
    ):
        return None, "invalid"
    custom_ids = [str(x) for x in payload.included_custom]
    referenced = [x[7:] for x in normalized if x.startswith("custom:")]
    if any(x not in referenced for x in custom_ids):
        return None, "invalid"
    async with conn.transaction():
        locked = await _one(
            conn,
            "SELECT render_payload FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s FOR UPDATE",
            (cid, user_id, payload.revision),
        )
        if not locked:
            return None, (
                "stale"
                if await _one(
                    conn,
                    "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",
                    (cid, user_id),
                )
                else "missing"
            )
        all_custom = [x[7:] for x in normalized if x.startswith("custom:")]
        owned = (
            await _many(
                conn,
                "SELECT id FROM custom_sections WHERE user_id=%s AND id=ANY(%s)",
                (user_id, all_custom),
            )
            if all_custom
            else []
        )
        if {str(x["id"]) for x in owned} != set(all_custom):
            return None, "missing"
        for sid in all_custom:
            await conn.execute(
                "INSERT INTO composition_custom_sections(composition_id,section_id,sort_order) VALUES(%s,%s,%s) ON CONFLICT(composition_id,section_id) DO UPDATE SET sort_order=excluded.sort_order",
                (cid, sid, normalized.index("custom:" + sid)),
            )
        resume = locked["render_payload"]
        resume["section_order"] = order
        resume["interest_layout"] = payload.interest_layout
        rendered = []
        for sid in all_custom:
            section = await _one(
                conn,
                "SELECT * FROM custom_sections WHERE id=%s AND user_id=%s",
                (sid, user_id),
            )
            entries = await _many(
                conn,
                "SELECT * FROM custom_section_entries WHERE section_id=%s AND user_id=%s ORDER BY sort_order,id",
                (sid, user_id),
            )
            rendered.append(_custom_render(section, entries))
        resume["custom_sections"] = rendered
        row = await _one(
            conn,
            "UPDATE resume_compositions SET render_payload=%s::jsonb,section_order=%s::jsonb,interest_layout=%s,revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s RETURNING *",
            (
                json.dumps(resume),
                json.dumps(order),
                payload.interest_layout,
                cid,
                user_id,
            ),
        )
        await conn.execute(
            "INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,'sections-panel',%s::jsonb)",
            (cid, user_id, row["revision"], json.dumps({"resume": resume})),
        )
        return row, None



async def reorder_composition_items(conn, user_id, cid, payload):
    allowed = {"education", "tool_groups", "projects", "work_experience", "leadership", "personal_interests"}
    if payload.section not in allowed:
        return None, "invalid"
    async with conn.transaction():
        locked = await _one(conn, "SELECT render_payload FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s FOR UPDATE", (cid, user_id, payload.revision))
        if not locked:
            exists = await _one(conn, "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL", (cid, user_id))
            return None, "stale" if exists else "missing"
        rows = await _many(conn, "SELECT item_id FROM composition_items WHERE composition_id=%s AND section=%s ORDER BY sort_order,id", (cid, payload.section))
        if {str(x["item_id"]) for x in rows} != {str(x) for x in payload.ids}:
            return None, "invalid"
        for index, rid in enumerate(payload.ids):
            await conn.execute("UPDATE composition_items SET sort_order=%s WHERE composition_id=%s AND section=%s AND item_id=%s", (index, cid, payload.section, rid))
        resume = locked["render_payload"]
        if payload.section == "education":
            ordered = await _many(conn, "SELECT e.* FROM composition_items i JOIN education_items e ON e.id=i.item_id WHERE i.composition_id=%s AND i.section='education' ORDER BY i.sort_order,i.id", (cid,))
            resume["education"] = [_education_render(x) for x in ordered]
            resume = await _apply_resume_placements(conn, user_id, cid, resume)
        elif payload.section == "tool_groups":
            resume["tool_groups"] = await _tool_groups_render(conn, user_id, payload.ids, cid)
        elif payload.section == "personal_interests":
            ordered = await _many(conn, "SELECT x.body FROM composition_items i JOIN interests x ON x.id=i.item_id WHERE i.composition_id=%s AND i.section='personal_interests' ORDER BY i.sort_order,i.id", (cid,))
            resume["personal_interests"] = [x["body"] for x in ordered]
        else:
            resume[payload.section] = [await render_historical_for_order(conn, user_id, rid, cid) for rid in payload.ids]
            resume = await _apply_resume_placements(conn, user_id, cid, resume)
        row = await _one(conn, "UPDATE resume_compositions SET render_payload=%s::jsonb,revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s RETURNING *", (json.dumps(resume), cid, user_id))
        await conn.execute("INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,'composition-item-reorder',%s::jsonb)", (cid,user_id,row["revision"],json.dumps({"resume":resume})))
        return row, None

async def render_historical_for_order(conn, user_id, item_id, cid):
    from .editing_repository import render_historical
    return await render_historical(conn, user_id, item_id, cid)

async def select_education(conn, user_id, cid, expected, education_id, included):
    async with conn.transaction():
        item = await _one(conn, "SELECT id,archived_at FROM education_items WHERE id=%s AND user_id=%s", (education_id,user_id))
        if not item or (included and item["archived_at"]): return None, "missing"
        locked = await _one(conn, "SELECT render_payload FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s FOR UPDATE", (cid,user_id,expected))
        if not locked:
            exists=await _one(conn,"SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",(cid,user_id))
            return None, "stale" if exists else "missing"
        if included:
            await conn.execute("INSERT INTO composition_items(composition_id,section,item_id,sort_order) VALUES(%s,'education',%s,(SELECT COALESCE(max(sort_order)+1,0) FROM composition_items WHERE composition_id=%s AND section='education')) ON CONFLICT DO NOTHING",(cid,education_id,cid))
        else:
            await conn.execute("DELETE FROM composition_items WHERE composition_id=%s AND section='education' AND item_id=%s",(cid,education_id))
        selected=await _many(conn,"SELECT e.* FROM composition_items i JOIN education_items e ON e.id=i.item_id WHERE i.composition_id=%s AND i.section='education' ORDER BY i.sort_order,i.id",(cid,))
        resume=locked["render_payload"]; resume["education"]=[_education_render(x) for x in selected]
        resume=await _apply_resume_placements(conn, user_id, cid, resume)
        row=await _one(conn,"UPDATE resume_compositions SET render_payload=%s::jsonb,revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s RETURNING *",(json.dumps(resume),cid,user_id))
        await conn.execute("INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,'education-selection',%s::jsonb)",(cid,user_id,row["revision"],json.dumps({"resume":resume})))
        return row,None


async def composition_items(conn,user_id,cid):
    exists=await _one(conn,"SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s",(cid,user_id))
    if not exists:return None
    return await _many(conn,"SELECT i.section,i.item_id,i.sort_order FROM composition_items i JOIN resume_compositions c ON c.id=i.composition_id WHERE i.composition_id=%s AND c.user_id=%s ORDER BY i.section,i.sort_order,i.id",(cid,user_id))

async def create_and_include_entry(conn,user_id,cid,payload):
    from types import SimpleNamespace
    section=payload.section; fields=payload.fields
    async with conn.transaction():
        locked=await _one(conn,"SELECT revision FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s FOR UPDATE",(cid,user_id,payload.revision))
        if not locked:
            return None,("stale" if await _one(conn,"SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",(cid,user_id)) else "missing")
        if section in {"projects","work_experience","leadership"}:
            kind={"projects":"project","work_experience":"employment","leadership":"leadership"}[section]
            from .editing_repository import add_item,select_historical
            rid=await add_item(conn,user_id,SimpleNamespace(kind=kind,bullets=[],**fields))
            return await select_historical(conn,user_id,cid,payload.revision,section,rid,True)
        creator={"education":create_education,"tool_groups":create_tool_group,"personal_interests":create_interest}.get(section)
        if not creator:return None,"invalid"
        row=await creator(conn,user_id,SimpleNamespace(**fields)); rid=row["id"]
        selector={"education":select_education,"tool_groups":select_tool_group,"personal_interests":select_interest}[section]
        result,error=await selector(conn,user_id,cid,payload.revision,rid,True)
        return result,error


async def load_skill_inputs(conn, user_id, cid):
    """Active Skills groups and every tool, shaped for skill_groups.recommend_group."""
    if not await _one(
        conn,
        "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",
        (cid, user_id),
    ):
        return None
    groups = await _many(
        conn,
        """SELECT g.id::text id,g.name,g.sort_order,
                  EXISTS(SELECT 1 FROM composition_items i WHERE i.composition_id=%s AND i.section='tool_groups' AND i.item_id=g.id) on_resume
           FROM tool_groups g WHERE g.user_id=%s AND g.archived_at IS NULL ORDER BY g.sort_order,g.id""",
        (cid, user_id),
    )
    tools = await _many(
        conn,
        """SELECT t.id::text id,t.name,t.group_id::text group_id,g.name group_name,
                  (t.archived_at IS NOT NULL OR g.archived_at IS NOT NULL) archived,
                  EXISTS(SELECT 1 FROM composition_hidden_tools h WHERE h.composition_id=%s AND h.tool_id=t.id) hidden_here
           FROM tools t JOIN tool_groups g ON g.id=t.group_id AND g.user_id=t.user_id
           WHERE t.user_id=%s ORDER BY g.sort_order,t.sort_order,t.id""",
        (cid, user_id),
    )
    return {"groups": groups, "tools": tools}


async def _unique_group_name(conn, user_id, base):
    name, number = base, 2
    while await _one(conn, "SELECT id FROM tool_groups WHERE user_id=%s AND name=%s", (user_id, name)):
        name = f"{base} {number}"
        number += 1
    return name


async def add_skill_to_resume(conn, user_id, cid, expected, name, group_id=None, new_group_name=None):
    """Add one skill to the library and to this resume only.

    Other resumes that include the group get a hidden row for a new or restored tool, so their
    payload, revision and history stay as they are.
    """
    label = " ".join((name or "").split())[:120]
    if not label:
        return None, "invalid"
    async with conn.transaction():
        locked = await _one(
            conn,
            "SELECT render_payload FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s FOR UPDATE",
            (cid, user_id, expected),
        )
        if not locked:
            return None, (
                "stale"
                if await _one(
                    conn,
                    "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",
                    (cid, user_id),
                )
                else "missing"
            )
        if group_id:
            group = await _one(
                conn,
                "SELECT id FROM tool_groups WHERE id=%s AND user_id=%s AND archived_at IS NULL",
                (group_id, user_id),
            )
            if not group:
                return None, "missing"
        else:
            wanted = " ".join((new_group_name or "").split())[:112]
            if not wanted:
                return None, "invalid"
            groups = await _many(
                conn,
                "SELECT id,name FROM tool_groups WHERE user_id=%s AND archived_at IS NULL",
                (user_id,),
            )
            # An active group that differs only by case is the same group.
            group = next((g for g in groups if g["name"].casefold() == wanted.casefold()), None)
            if not group:
                group = await _one(
                    conn,
                    "INSERT INTO tool_groups(user_id,name,sort_order) VALUES(%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM tool_groups WHERE user_id=%s)) RETURNING id",
                    (user_id, await _unique_group_name(conn, user_id, wanted), user_id),
                )
        gid = group["id"]

        tools = await _many(
            conn,
            "SELECT id,name,group_id,archived_at FROM tools WHERE user_id=%s ORDER BY (archived_at IS NULL) DESC,sort_order,id",
            (user_id,),
        )
        same = [t for t in tools if same_skill(t["name"], label)]
        here = next((t for t in same if str(t["group_id"]) == str(gid)), None)
        archived_elsewhere = next((t for t in same if t["archived_at"] and str(t["group_id"]) != str(gid)), None)
        newly_visible = True
        if here and not here["archived_at"]:
            tool_id = here["id"]
            newly_visible = False
        elif here:
            tool_id = here["id"]
            await conn.execute(
                "UPDATE tools SET archived_at=NULL,updated_at=now() WHERE id=%s AND user_id=%s",
                (tool_id, user_id),
            )
        elif archived_elsewhere:
            # An archived row is on no resume, so moving it into the chosen group is safe.
            tool_id = archived_elsewhere["id"]
            await conn.execute(
                "UPDATE tools SET archived_at=NULL,group_id=%s,sort_order=(SELECT COALESCE(max(sort_order)+1,0) FROM tools WHERE group_id=%s),updated_at=now() WHERE id=%s AND user_id=%s",
                (gid, gid, tool_id, user_id),
            )
        else:
            # Never move an active tool from another group: that would change other resumes.
            tool_id = (
                await _one(
                    conn,
                    "INSERT INTO tools(user_id,group_id,name,sort_order) VALUES(%s,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM tools WHERE group_id=%s)) RETURNING id",
                    (user_id, gid, label, gid),
                )
            )["id"]

        member = await _one(
            conn,
            "SELECT 1 FROM composition_items WHERE composition_id=%s AND section='tool_groups' AND item_id=%s",
            (cid, gid),
        )
        if not member:
            await conn.execute(
                "INSERT INTO composition_items(composition_id,section,item_id,sort_order) VALUES(%s,'tool_groups',%s,(SELECT COALESCE(max(sort_order)+1,0) FROM composition_items WHERE composition_id=%s AND section='tool_groups'))",
                (cid, gid, cid),
            )
            # The user asked for one skill, so the rest of a newly added group stays hidden here.
            await conn.execute(
                "INSERT INTO composition_hidden_tools(composition_id,tool_id) SELECT %s,t.id FROM tools t WHERE t.group_id=%s AND t.user_id=%s AND t.id<>%s ON CONFLICT DO NOTHING",
                (cid, gid, user_id, tool_id),
            )
        await conn.execute(
            "DELETE FROM composition_hidden_tools WHERE composition_id=%s AND tool_id=%s",
            (cid, tool_id),
        )
        if newly_visible:
            await conn.execute(
                """INSERT INTO composition_hidden_tools(composition_id,tool_id)
                   SELECT i.composition_id,%s FROM composition_items i
                   JOIN resume_compositions c ON c.id=i.composition_id AND c.user_id=%s
                   WHERE i.section='tool_groups' AND i.item_id=%s AND i.composition_id<>%s
                   ON CONFLICT DO NOTHING""",
                (tool_id, user_id, gid, cid),
            )

        selected = await _many(
            conn,
            "SELECT item_id FROM composition_items WHERE composition_id=%s AND section='tool_groups' ORDER BY sort_order,id",
            (cid,),
        )
        resume = locked["render_payload"]
        resume["tool_groups"] = await _tool_groups_render(
            conn, user_id, [x["item_id"] for x in selected], cid
        )
        row = await _one(
            conn,
            "UPDATE resume_compositions SET render_payload=%s::jsonb,revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s RETURNING *",
            (json.dumps(resume), cid, user_id),
        )
        await conn.execute(
            "INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,'skill-add',%s::jsonb)",
            (cid, user_id, row["revision"], json.dumps({"resume": resume})),
        )
        return row, None
