"""Resume variants, field variants, and bullet save/conversion choices."""

import json
from .editing_repository import many, one, render_historical
from .library_repository import (
    _custom_render,
    _education_render,
    _profile_header,
    _tool_group_render,
)
from .phase2j_repository import _commit, _lock_composition, apply_placements


async def _unique_name(conn, sql, params, base):
    name, number = base, 2
    while await one(conn, sql, (*params, name)):
        name = f"{base} {number}"
        number += 1
    return name


async def _insert_sibling_bullet(conn, user_id, bullet_id):
    return await one(
        conn,
        """INSERT INTO bullets(
             user_id,parent_id,education_item_id,tool_group_id,interest_id,custom_entry_id,
             section,parent_context,sort_order
           )
           SELECT %s,b.parent_id,b.education_item_id,b.tool_group_id,b.interest_id,b.custom_entry_id,
                  b.section,b.parent_context,
                  (SELECT COALESCE(max(sort_order)+1,0) FROM bullets s
                   WHERE s.user_id=%s
                     AND s.parent_id IS NOT DISTINCT FROM b.parent_id
                     AND s.education_item_id IS NOT DISTINCT FROM b.education_item_id
                     AND s.tool_group_id IS NOT DISTINCT FROM b.tool_group_id
                     AND s.interest_id IS NOT DISTINCT FROM b.interest_id
                     AND s.custom_entry_id IS NOT DISTINCT FROM b.custom_entry_id)
           FROM bullets b WHERE b.id=%s AND b.user_id=%s
           RETURNING id""",
        (user_id, user_id, bullet_id, user_id),
    )


async def default_starter(conn, user_id):
    return await one(
        conn,
        """SELECT id FROM resume_compositions
           WHERE user_id=%s AND is_starter AND is_default_starter AND archived_at IS NULL""",
        (user_id,),
    )


async def apply_library_defaults(conn, user_id, composition_id):
    """Fill a new resume with the library's default profile, summary, entries, and wording."""
    async with conn.transaction():
        row = await one(
            conn,
            "SELECT * FROM resume_compositions WHERE id=%s AND user_id=%s FOR UPDATE",
            (composition_id, user_id),
        )
        if not row:
            return None
        profile_variant = await one(
            conn,
            """SELECT v.id,v.profile_id,v.display_name AS name,v.phone,v.email,
                      v.linkedin_label,v.linkedin_url
               FROM profile_field_variants v
               JOIN profiles p ON p.id=v.profile_id AND p.user_id=v.user_id
               WHERE v.user_id=%s AND v.is_default AND v.archived_at IS NULL AND p.archived_at IS NULL
               ORDER BY v.sort_order,v.id LIMIT 1""",
            (user_id,),
        )
        profile = None
        if profile_variant:
            profile_id, profile_variant_id = profile_variant["profile_id"], profile_variant["id"]
            header = _profile_header(profile_variant)
        else:
            profile = await one(
                conn,
                """SELECT id,name,phone,email,linkedin_label,linkedin_url
                   FROM profiles WHERE user_id=%s AND archived_at IS NULL
                   ORDER BY (lower(label)='default') DESC, sort_order, id LIMIT 1""",
                (user_id,),
            )
            profile_id = profile["id"] if profile else None
            profile_variant_id = None
            header = _profile_header(profile) if profile else row["render_payload"].get("header") or {}
        summary = await one(
            conn,
            """SELECT id,body FROM summary_variants
               WHERE user_id=%s AND archived_at IS NULL
               ORDER BY (lower(name)='default') DESC, sort_order, id LIMIT 1""",
            (user_id,),
        )
        await conn.execute(
            """INSERT INTO composition_items(composition_id,section,item_id,variant_id,sort_order)
               SELECT %s, CASE c.kind
                        WHEN 'project' THEN 'projects'
                        WHEN 'employment' THEN 'work_experience'
                        ELSE 'leadership' END,
                      c.id, v.id,
                      row_number() OVER (PARTITION BY c.kind ORDER BY c.sort_order, c.id) - 1
               FROM content_items c
               LEFT JOIN LATERAL (
                 SELECT id FROM content_item_variants
                 WHERE content_item_id=c.id AND user_id=c.user_id AND archived_at IS NULL AND is_default
                 ORDER BY sort_order, id LIMIT 1
               ) v ON true
               WHERE c.user_id=%s AND c.archived_at IS NULL
                 AND c.kind IN ('project','employment','leadership')""",
            (composition_id, user_id),
        )
        await conn.execute(
            """INSERT INTO composition_items(composition_id,section,item_id,variant_id,sort_order)
               SELECT %s,'education',e.id,v.id,
                      row_number() OVER (ORDER BY e.sort_order, e.id) - 1
               FROM education_items e
               LEFT JOIN LATERAL (
                 SELECT id FROM education_item_variants
                 WHERE education_item_id=e.id AND user_id=e.user_id AND archived_at IS NULL AND is_default
                 ORDER BY sort_order, id LIMIT 1
               ) v ON true
               WHERE e.user_id=%s AND e.archived_at IS NULL""",
            (composition_id, user_id),
        )
        await conn.execute(
            """INSERT INTO composition_items(composition_id,section,item_id,sort_order)
               SELECT %s,'tool_groups',g.id, row_number() OVER (ORDER BY g.sort_order, g.id) - 1
               FROM tool_groups g WHERE g.user_id=%s AND g.archived_at IS NULL""",
            (composition_id, user_id),
        )
        await conn.execute(
            """INSERT INTO composition_items(composition_id,section,item_id,sort_order)
               SELECT %s,'personal_interests',i.id, row_number() OVER (ORDER BY i.sort_order, i.id) - 1
               FROM interests i WHERE i.user_id=%s AND i.archived_at IS NULL""",
            (composition_id, user_id),
        )
        await conn.execute(
            """INSERT INTO composition_custom_sections(composition_id,section_id,sort_order)
               SELECT %s,s.id, row_number() OVER (ORDER BY s.sort_order, s.id) - 1
               FROM custom_sections s WHERE s.user_id=%s AND s.archived_at IS NULL""",
            (composition_id, user_id),
        )
        await conn.execute(
            """INSERT INTO composition_bullets(
                 composition_id,bullet_id,variant_id,destination_section,destination_parent_type,
                 destination_parent_id,sort_order,wording_snapshot,snapshot_source_updated_at
               )
               SELECT %s,b.id,v.id,src.section,src.parent_type,src.parent_id,
                      row_number() OVER (PARTITION BY src.parent_id ORDER BY b.sort_order, b.id) - 1,
                      v.body,v.updated_at
               FROM bullets b
               JOIN LATERAL (
                 SELECT id,body,updated_at FROM bullet_variants
                 WHERE bullet_id=b.id AND user_id=b.user_id AND archived_at IS NULL
                 ORDER BY is_default DESC, sort_order, id LIMIT 1
               ) v ON true
               JOIN (
                 SELECT id parent_id,'content_item' parent_type,
                        CASE kind WHEN 'project' THEN 'projects'
                                  WHEN 'employment' THEN 'work_experience'
                                  ELSE 'leadership' END section
                 FROM content_items
                 WHERE user_id=%s AND archived_at IS NULL AND kind IN ('project','employment','leadership')
                 UNION ALL
                 SELECT id,'education_item','education' FROM education_items
                 WHERE user_id=%s AND archived_at IS NULL
                 UNION ALL
                 SELECT id,'tool_group','tool_groups' FROM tool_groups
                 WHERE user_id=%s AND archived_at IS NULL
                 UNION ALL
                 SELECT id,'interest','personal_interests' FROM interests
                 WHERE user_id=%s AND archived_at IS NULL
                 UNION ALL
                 SELECT e.id,'custom_entry','custom_sections'
                 FROM custom_section_entries e
                 JOIN custom_sections s ON s.id=e.section_id
                 WHERE e.user_id=%s AND e.archived_at IS NULL AND s.archived_at IS NULL
               ) src ON (
                 (src.parent_type='content_item' AND b.parent_id=src.parent_id) OR
                 (src.parent_type='education_item' AND b.education_item_id=src.parent_id) OR
                 (src.parent_type='tool_group' AND b.tool_group_id=src.parent_id) OR
                 (src.parent_type='interest' AND b.interest_id=src.parent_id) OR
                 (src.parent_type='custom_entry' AND b.custom_entry_id=src.parent_id)
               )
               WHERE b.user_id=%s AND b.archived_at IS NULL""",
            (composition_id, user_id, user_id, user_id, user_id, user_id, user_id),
        )
        resume = dict(row["render_payload"])
        for section in ("projects", "work_experience", "leadership"):
            selected = await many(
                conn,
                """SELECT item_id FROM composition_items
                   WHERE composition_id=%s AND section=%s ORDER BY sort_order,id""",
                (composition_id, section),
            )
            resume[section] = [
                await render_historical(conn, user_id, item["item_id"], composition_id)
                for item in selected
            ]
        education = await many(
            conn,
            """SELECT e.*, v.institution v_institution, v.college_school v_college, v.location v_location,
                      v.degree_type v_degree_type, v.degree_major v_degree_major, v.degree v_degree,
                      v.graduation_year v_year, v.graduation_month v_month, v.display_date v_display,
                      v.graduation_date v_graduation
               FROM composition_items i
               JOIN education_items e ON e.id=i.item_id
               LEFT JOIN education_item_variants v ON v.id=i.variant_id
               WHERE i.composition_id=%s AND i.section='education'
               ORDER BY i.sort_order,i.id""",
            (composition_id,),
        )
        rendered_education = []
        for item in education:
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
            rendered_education.append(_education_render(item))
        resume["education"] = rendered_education
        groups = await many(
            conn,
            """SELECT item_id FROM composition_items
               WHERE composition_id=%s AND section='tool_groups' ORDER BY sort_order,id""",
            (composition_id,),
        )
        resume["tool_groups"] = [
            await _tool_group_render(conn, user_id, item["item_id"], composition_id)
            for item in groups
        ]
        interests = await many(
            conn,
            """SELECT x.body FROM composition_items i
               JOIN interests x ON x.id=i.item_id
               WHERE i.composition_id=%s AND i.section='personal_interests'
               ORDER BY i.sort_order,i.id""",
            (composition_id,),
        )
        resume["personal_interests"] = [item["body"] for item in interests]
        custom = await many(
            conn,
            """SELECT s.* FROM composition_custom_sections x
               JOIN custom_sections s ON s.id=x.section_id
               WHERE x.composition_id=%s ORDER BY x.sort_order,x.id""",
            (composition_id,),
        )
        rendered_custom = []
        for section in custom:
            entries = await many(
                conn,
                """SELECT * FROM custom_section_entries
                   WHERE section_id=%s AND user_id=%s ORDER BY sort_order,id""",
                (section["id"], user_id),
            )
            rendered_custom.append(_custom_render(section, entries))
        resume["custom_sections"] = rendered_custom
        order = list(resume.get("section_order") or [])
        for section in custom:
            key = f"custom:{section['id']}"
            if key not in order:
                order.append(key)
        resume["section_order"] = order
        if summary:
            resume["summary"] = summary["body"]
        if header:
            resume["header"] = header
        resume = await apply_placements(conn, user_id, composition_id, resume)
        saved = await one(
            conn,
            """UPDATE resume_compositions
               SET profile_id=%s,profile_variant_id=%s,summary_variant_id=%s,
                   render_payload=%s::jsonb,revision=revision+1,updated_at=now()
               WHERE id=%s RETURNING *""",
            (
                profile_id,
                profile_variant_id,
                summary["id"] if summary else None,
                json.dumps(resume),
                composition_id,
            ),
        )
        await conn.execute(
            """INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot)
               VALUES(%s,%s,%s,'library-defaults',%s::jsonb)""",
            (
                composition_id,
                user_id,
                saved["revision"],
                json.dumps({"resume": resume, "name": saved["name"]}),
            ),
        )
        return saved


async def _copy_rows(conn, source_id, target_id):
    await conn.execute("DELETE FROM composition_items WHERE composition_id=%s", (target_id,))
    await conn.execute("DELETE FROM composition_bullets WHERE composition_id=%s", (target_id,))
    await conn.execute(
        "DELETE FROM composition_custom_sections WHERE composition_id=%s", (target_id,)
    )
    await conn.execute(
        """INSERT INTO composition_items(composition_id,section,item_id,variant_id,sort_order)
           SELECT %s,section,item_id,variant_id,sort_order FROM composition_items WHERE composition_id=%s""",
        (target_id, source_id),
    )
    await conn.execute(
        """INSERT INTO composition_bullets(
             composition_id,bullet_id,variant_id,destination_section,destination_parent_type,
             destination_parent_id,sort_order,wording_snapshot,snapshot_source_updated_at
           )
           SELECT %s,bullet_id,variant_id,destination_section,destination_parent_type,
                  destination_parent_id,sort_order,wording_snapshot,snapshot_source_updated_at
           FROM composition_bullets WHERE composition_id=%s""",
        (target_id, source_id),
    )
    await conn.execute(
        """INSERT INTO composition_custom_sections(composition_id,section_id,sort_order)
           SELECT %s,section_id,sort_order FROM composition_custom_sections WHERE composition_id=%s""",
        (target_id, source_id),
    )


async def copy_resume_variant(conn, user_id, starter_id, name, description, display_title, target_company, target_role):
    async with conn.transaction():
        source = await one(
            conn,
            "SELECT * FROM resume_compositions WHERE id=%s AND user_id=%s AND is_starter AND archived_at IS NULL",
            (starter_id, user_id),
        )
        if not source:
            return None
        if name:
            internal = name.strip()
        else:
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(user_id),))
            from datetime import date

            base = f"{(display_title or source.get('display_title') or 'Resume').strip() or 'Resume'} ({date.today().strftime('%m/%d/%Y')})"
            existing = await many(
                conn,
                "SELECT name FROM resume_compositions WHERE user_id=%s AND (name=%s OR name LIKE %s)",
                (user_id, base, base + " (%)"),
            )
            used = {row["name"] for row in existing}
            internal, suffix = base, 2
            while internal in used:
                internal = f"{base} ({suffix})"
                suffix += 1
        row = await one(
            conn,
            """INSERT INTO resume_compositions(
                 user_id,name,description,display_title,target_company,target_role,
                 summary_variant_id,profile_id,profile_variant_id,render_payload,
                 interest_layout,section_order,preferred_page_length,date_format,
                 template_style,skill_row_max,section_sort_modes,is_starter,is_default_starter
               )
               SELECT user_id,%s,%s,%s,%s,%s,summary_variant_id,profile_id,profile_variant_id,
                      render_payload,interest_layout,section_order,preferred_page_length,date_format,
                      template_style,skill_row_max,section_sort_modes,false,false
               FROM resume_compositions WHERE id=%s
               RETURNING *""",
            (
                internal,
                description or source.get("description") or "",
                display_title or source.get("display_title") or "",
                target_company or source.get("target_company") or "",
                target_role or source.get("target_role") or "",
                starter_id,
            ),
        )
        await _copy_rows(conn, starter_id, row["id"])
        await conn.execute(
            """INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot)
               VALUES(%s,%s,%s,'create',%s::jsonb)""",
            (row["id"], user_id, row["revision"], json.dumps({"resume": row["render_payload"], "name": row["name"]})),
        )
        return row


async def save_as_resume_variant(conn, user_id, cid, name, replace_id=None):
    async with conn.transaction():
        source = await one(
            conn,
            "SELECT * FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL AND NOT is_starter",
            (cid, user_id),
        )
        if not source:
            return None, "missing"
        taken = await one(
            conn,
            "SELECT id FROM resume_compositions WHERE user_id=%s AND name=%s AND id IS DISTINCT FROM %s",
            (user_id, name.strip(), replace_id),
        )
        if taken:
            return None, "name"
        if replace_id:
            starter = await one(
                conn,
                "SELECT * FROM resume_compositions WHERE id=%s AND user_id=%s AND is_starter AND archived_at IS NULL FOR UPDATE",
                (replace_id, user_id),
            )
            if not starter:
                return None, "missing"
            row = await one(
                conn,
                """UPDATE resume_compositions SET name=%s,description=%s,display_title=%s,
                     target_company=%s,target_role=%s,
                     summary_variant_id=%s,profile_id=%s,profile_variant_id=%s,render_payload=%s::jsonb,
                     interest_layout=%s,section_order=%s,preferred_page_length=%s,date_format=%s,
                     template_style=%s,skill_row_max=%s,section_sort_modes=%s,revision=revision+1,updated_at=now()
                   WHERE id=%s RETURNING *""",
                (
                    name.strip(),
                    source.get("description") or "",
                    source.get("display_title") or "",
                    source.get("target_company") or "",
                    source.get("target_role") or "",
                    source.get("summary_variant_id"),
                    source.get("profile_id"),
                    source.get("profile_variant_id"),
                    json.dumps(source["render_payload"]),
                    source.get("interest_layout") or "compact",
                    json.dumps(source.get("section_order") or []),
                    source.get("preferred_page_length") or 1,
                    source.get("date_format") or "long",
                    source.get("template_style") or "classic",
                    source.get("skill_row_max") or 4,
                    json.dumps(source.get("section_sort_modes") or {}),
                    replace_id,
                ),
            )
            await _copy_rows(conn, cid, replace_id)
            return row, None
        has_default = await default_starter(conn, user_id)
        row = await one(
            conn,
            """INSERT INTO resume_compositions(
                 user_id,name,description,display_title,target_company,target_role,summary_variant_id,profile_id,profile_variant_id,
                 render_payload,interest_layout,section_order,preferred_page_length,date_format,
                 template_style,skill_row_max,section_sort_modes,is_starter,is_default_starter
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s,%s,%s,%s,%s::jsonb,true,%s)
               RETURNING *""",
            (
                user_id,
                name.strip(),
                source.get("description") or "",
                source.get("display_title") or "",
                source.get("target_company") or "",
                source.get("target_role") or "",
                source.get("summary_variant_id"),
                source.get("profile_id"),
                source.get("profile_variant_id"),
                json.dumps(source["render_payload"]),
                source.get("interest_layout") or "compact",
                json.dumps(source.get("section_order") or []),
                source.get("preferred_page_length") or 1,
                source.get("date_format") or "long",
                source.get("template_style") or "classic",
                source.get("skill_row_max") or 4,
                json.dumps(source.get("section_sort_modes") or {}),
                not bool(has_default),
            ),
        )
        await _copy_rows(conn, cid, row["id"])
        return row, None


async def set_default_resume_variant(conn, user_id, cid):
    async with conn.transaction():
        row = await one(
            conn,
            "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND is_starter AND archived_at IS NULL",
            (cid, user_id),
        )
        if not row:
            return None
        await conn.execute(
            "UPDATE resume_compositions SET is_default_starter=false,updated_at=now() WHERE user_id=%s AND is_starter",
            (user_id,),
        )
        return await one(
            conn,
            "UPDATE resume_compositions SET is_default_starter=true,updated_at=now() WHERE id=%s RETURNING *",
            (cid,),
        )


async def rerender(conn, user_id, cid, source):
    row = await one(
        conn,
        "SELECT * FROM resume_compositions WHERE id=%s AND user_id=%s",
        (cid, user_id),
    )
    if not row:
        return None
    resume = dict(row["render_payload"])
    selected = await many(
        conn,
        """SELECT i.section,i.item_id FROM composition_items i
           WHERE i.composition_id=%s AND i.section IN ('projects','work_experience','leadership')
           ORDER BY i.section,i.sort_order,i.id""",
        (cid,),
    )
    for section in ("projects", "work_experience", "leadership"):
        resume[section] = [
            await render_historical(conn, user_id, item["item_id"], cid)
            for item in selected
            if item["section"] == section
        ]
    education = await many(
        conn,
        """SELECT e.*, v.institution v_institution, v.college_school v_college, v.location v_location,
                  v.degree_type v_degree_type, v.degree_major v_degree_major, v.degree v_degree,
                  v.graduation_year v_year, v.graduation_month v_month, v.display_date v_display,
                  v.graduation_date v_graduation
           FROM composition_items i
           JOIN education_items e ON e.id=i.item_id
           LEFT JOIN education_item_variants v ON v.id=i.variant_id
           WHERE i.composition_id=%s AND i.section='education'
           ORDER BY i.sort_order,i.id""",
        (cid,),
    )
    rendered = []
    for item in education:
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
    if education:
        resume["education"] = rendered
    if row.get("profile_variant_id"):
        variant = await one(
            conn,
            "SELECT display_name AS name,phone,email,linkedin_label,linkedin_url FROM profile_field_variants WHERE id=%s AND user_id=%s",
            (row["profile_variant_id"], user_id),
        )
        if variant:
            resume["header"] = _profile_header(variant)
    elif row.get("profile_id"):
        profile = await one(
            conn,
            "SELECT name,phone,email,linkedin_label,linkedin_url FROM profiles WHERE id=%s AND user_id=%s",
            (row["profile_id"], user_id),
        )
        if profile:
            resume["header"] = _profile_header(profile)
    resume = await apply_placements(conn, user_id, cid, resume)
    saved = await one(
        conn,
        """UPDATE resume_compositions SET render_payload=%s::jsonb,revision=revision+1,autosaved_at=now(),updated_at=now()
           WHERE id=%s AND user_id=%s RETURNING *""",
        (json.dumps(resume), cid, user_id),
    )
    await conn.execute(
        """INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot)
           VALUES(%s,%s,%s,%s,%s::jsonb)""",
        (cid, user_id, saved["revision"], source, json.dumps({"resume": resume})),
    )
    return saved


async def save_bullet_edit(conn, user_id, cid, placement_id, revision, body, mode):
    async with conn.transaction():
        locked, error = await _lock_composition(conn, user_id, cid, revision)
        if error:
            return None, error
        placement = await one(
            conn,
            """SELECT cb.*, b.parent_id, b.section FROM composition_bullets cb
               JOIN bullets b ON b.id=cb.bullet_id
               WHERE cb.id=%s AND cb.composition_id=%s""",
            (placement_id, cid),
        )
        if not placement:
            return None, "missing"
        text = body.strip()
        if mode == "overwrite":
            await conn.execute(
                "UPDATE bullet_variants SET body=%s,updated_at=now() WHERE id=%s AND user_id=%s",
                (text, placement["variant_id"], user_id),
            )
            await conn.execute(
                """UPDATE composition_bullets SET wording_snapshot=%s,snapshot_source_updated_at=now(),updated_at=now()
                   WHERE id=%s""",
                (text, placement_id),
            )
        elif mode == "new":
            bullet = await _insert_sibling_bullet(conn, user_id, placement["bullet_id"])
            variant = await one(
                conn,
                """INSERT INTO bullet_variants(user_id,bullet_id,name,body,is_default,sort_order)
                   VALUES(%s,%s,'Default',%s,true,0) RETURNING id""",
                (user_id, bullet["id"], text),
            )
            await conn.execute(
                """UPDATE composition_bullets SET bullet_id=%s,variant_id=%s,wording_snapshot=%s,
                     snapshot_source_updated_at=now(),updated_at=now() WHERE id=%s""",
                (bullet["id"], variant["id"], text, placement_id),
            )
        else:
            name = await _unique_name(
                conn,
                "SELECT id FROM bullet_variants WHERE bullet_id=%s AND name=%s",
                (placement["bullet_id"],),
                "Variant",
            )
            variant = await one(
                conn,
                """INSERT INTO bullet_variants(user_id,bullet_id,name,body,is_default,sort_order)
                   VALUES(%s,%s,%s,%s,false,(SELECT COALESCE(max(sort_order)+1,0) FROM bullet_variants WHERE bullet_id=%s))
                   RETURNING id""",
                (user_id, placement["bullet_id"], name, text, placement["bullet_id"]),
            )
            await conn.execute(
                """UPDATE composition_bullets SET variant_id=%s,wording_snapshot=%s,snapshot_source_updated_at=now(),updated_at=now()
                   WHERE id=%s""",
                (variant["id"], text, placement_id),
            )
        return await _commit(conn, user_id, locked, f"bullet-save-{mode}"), None


def _content_fields(fields):
    return (
        fields.get("name"),
        fields.get("subtitle"),
        fields.get("organization"),
        fields.get("location") or "",
        fields.get("title"),
        (fields.get("date_label") or "").strip(),
        fields.get("start_year"),
        fields.get("start_month"),
        fields.get("end_year"),
        fields.get("end_month"),
        bool(fields.get("is_current")),
    )


async def save_entry_edit(conn, user_id, cid, item_id, revision, section, fields, mode):
    async with conn.transaction():
        locked, error = await _lock_composition(conn, user_id, cid, revision)
        if error:
            return None, error
        link = await one(
            conn,
            "SELECT id,variant_id FROM composition_items WHERE composition_id=%s AND section=%s AND item_id=%s",
            (cid, section, item_id),
        )
        if not link:
            return None, "missing"
        if section == "education":
            await _save_education(conn, user_id, cid, item_id, fields, mode)
        else:
            await _save_content(conn, user_id, cid, item_id, section, fields, mode)
        return await rerender(conn, user_id, cid, f"entry-save-{mode}"), None


async def _save_content(conn, user_id, cid, item_id, section, fields, mode):
    kind = {"projects": "project", "leadership": "leadership"}.get(section, "employment")
    values = _content_fields(fields)
    if mode == "overwrite":
        await conn.execute(
            """UPDATE content_items SET name=%s,subtitle=%s,organization=%s,location=%s,title=%s,date_label=%s,
                 start_year=%s,start_month=%s,end_year=%s,end_month=%s,is_current=%s,updated_at=now()
               WHERE id=%s AND user_id=%s""",
            (*values, item_id, user_id),
        )
        return
    if mode == "new":
        created = await one(
            conn,
            """INSERT INTO content_items(
                 user_id,kind,name,subtitle,organization,location,title,date_label,
                 start_year,start_month,end_year,end_month,is_current,sort_order
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                 (SELECT COALESCE(max(sort_order)+1,0) FROM content_items WHERE user_id=%s AND kind=%s))
               RETURNING id""",
            (user_id, kind, *values, user_id, kind),
        )
        await conn.execute(
            "UPDATE composition_items SET item_id=%s,variant_id=NULL WHERE composition_id=%s AND item_id=%s",
            (created["id"], cid, item_id),
        )
        await conn.execute(
            """UPDATE composition_bullets SET destination_parent_id=%s,updated_at=now()
               WHERE composition_id=%s AND destination_parent_id=%s""",
            (created["id"], cid, item_id),
        )
        return
    name = await _unique_name(
        conn,
        "SELECT id FROM content_item_variants WHERE content_item_id=%s AND name=%s",
        (item_id,),
        "Variant",
    )
    variant = await one(
        conn,
        """INSERT INTO content_item_variants(
             user_id,content_item_id,name,item_name,subtitle,organization,location,title,date_label,
             start_year,start_month,end_year,end_month,is_current,is_default,sort_order
           ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false,
             (SELECT COALESCE(max(sort_order)+1,0) FROM content_item_variants WHERE content_item_id=%s))
           RETURNING id""",
        (user_id, item_id, name, *values, item_id),
    )
    await conn.execute(
        "UPDATE composition_items SET variant_id=%s WHERE composition_id=%s AND section=%s AND item_id=%s",
        (variant["id"], cid, section, item_id),
    )


async def _save_education(conn, user_id, cid, item_id, fields, mode):
    major = (fields.get("degree_major") or "").strip()
    display = (fields.get("display_date") or "").strip()
    graduation = display or (str(fields.get("graduation_year")) if fields.get("graduation_year") else "")
    values = (
        (fields.get("institution") or "").strip(),
        (fields.get("college_school") or "").strip() or None,
        fields.get("location") or "",
        (fields.get("degree_type") or "").strip() or None,
        major or None,
        major,
        fields.get("graduation_year"),
        fields.get("graduation_month"),
        display or None,
        graduation,
    )
    if mode == "overwrite":
        await conn.execute(
            """UPDATE education_items SET institution=%s,college_school=%s,location=%s,degree_type=%s,degree_major=%s,
                 degree=%s,graduation_year=%s,graduation_month=%s,display_date=%s,graduation_date=%s,updated_at=now()
               WHERE id=%s AND user_id=%s""",
            (*values, item_id, user_id),
        )
        return
    if mode == "new":
        created = await one(
            conn,
            """INSERT INTO education_items(
                 user_id,institution,college_school,location,degree_type,degree_major,degree,
                 graduation_year,graduation_month,display_date,graduation_date,sort_order
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                 (SELECT COALESCE(max(sort_order)+1,0) FROM education_items WHERE user_id=%s))
               RETURNING id""",
            (user_id, *values, user_id),
        )
        await conn.execute(
            "UPDATE composition_items SET item_id=%s,variant_id=NULL WHERE composition_id=%s AND section='education' AND item_id=%s",
            (created["id"], cid, item_id),
        )
        await conn.execute(
            """UPDATE composition_bullets SET destination_parent_id=%s,updated_at=now()
               WHERE composition_id=%s AND destination_parent_id=%s""",
            (created["id"], cid, item_id),
        )
        return
    name = await _unique_name(
        conn,
        "SELECT id FROM education_item_variants WHERE education_item_id=%s AND name=%s",
        (item_id,),
        "Variant",
    )
    variant = await one(
        conn,
        """INSERT INTO education_item_variants(
             user_id,education_item_id,name,institution,college_school,location,degree_type,degree_major,degree,
             graduation_year,graduation_month,display_date,graduation_date,is_default,sort_order
           ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false,
             (SELECT COALESCE(max(sort_order)+1,0) FROM education_item_variants WHERE education_item_id=%s))
           RETURNING id""",
        (user_id, item_id, name, *values, item_id),
    )
    await conn.execute(
        "UPDATE composition_items SET variant_id=%s WHERE composition_id=%s AND section='education' AND item_id=%s",
        (variant["id"], cid, item_id),
    )


async def save_summary_edit(conn, user_id, cid, summary_id, revision, name, body, mode):
    async with conn.transaction():
        locked, error = await _lock_composition(conn, user_id, cid, revision)
        if error:
            return None, error
        text, label = body.strip(), name.strip()
        if mode == "overwrite":
            await conn.execute(
                "UPDATE summary_variants SET name=%s,body=%s,updated_at=now() WHERE id=%s AND user_id=%s",
                (label, text, summary_id, user_id),
            )
            target = summary_id
        else:
            variant_name = await _unique_name(
                conn,
                "SELECT id FROM summary_variants WHERE user_id=%s AND name=%s",
                (user_id,),
                label if mode == "new" else f"Variant of {label}",
            )
            created = await one(
                conn,
                """INSERT INTO summary_variants(user_id,name,body,sort_order)
                   VALUES(%s,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM summary_variants WHERE user_id=%s))
                   RETURNING id""",
                (user_id, variant_name, text, user_id),
            )
            target = created["id"]
        row = await one(
            conn,
            """UPDATE resume_compositions SET summary_variant_id=%s,
                 render_payload=jsonb_set(render_payload,'{summary}',to_jsonb(%s::text)),
                 revision=revision+1,autosaved_at=now(),updated_at=now()
               WHERE id=%s AND user_id=%s RETURNING *""",
            (target, text, cid, user_id),
        )
        return row, None


async def save_profile_edit(conn, user_id, cid, profile_id, revision, fields, mode):
    async with conn.transaction():
        locked, error = await _lock_composition(conn, user_id, cid, revision)
        if error:
            return None, error
        values = (
            (fields.get("name") or "").strip(),
            fields.get("phone") or "",
            fields.get("email") or "",
            fields.get("linkedin_label") or "",
            fields.get("linkedin_url") or "",
        )
        if mode == "overwrite":
            await conn.execute(
                """UPDATE profiles SET name=%s,phone=%s,email=%s,linkedin_label=%s,linkedin_url=%s,updated_at=now()
                   WHERE id=%s AND user_id=%s""",
                (*values, profile_id, user_id),
            )
            await conn.execute(
                "UPDATE resume_compositions SET profile_variant_id=NULL WHERE id=%s",
                (cid,),
            )
        elif mode == "new":
            label = await _unique_name(
                conn,
                "SELECT id FROM profiles WHERE user_id=%s AND label=%s",
                (user_id,),
                f"{values[0] or 'Profile'} copy",
            )
            created = await one(
                conn,
                """INSERT INTO profiles(user_id,label,name,phone,email,linkedin_label,linkedin_url,sort_order)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM profiles WHERE user_id=%s))
                   RETURNING id""",
                (user_id, label, *values, user_id),
            )
            await conn.execute(
                "UPDATE resume_compositions SET profile_id=%s,profile_variant_id=NULL WHERE id=%s",
                (created["id"], cid),
            )
        else:
            variant_name = await _unique_name(
                conn,
                "SELECT id FROM profile_field_variants WHERE profile_id=%s AND name=%s",
                (profile_id,),
                "Variant",
            )
            created = await one(
                conn,
                """INSERT INTO profile_field_variants(
                     user_id,profile_id,name,display_name,phone,email,linkedin_label,linkedin_url,sort_order
                   ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,
                     (SELECT COALESCE(max(sort_order)+1,0) FROM profile_field_variants WHERE profile_id=%s))
                   RETURNING id""",
                (user_id, profile_id, variant_name, *values, profile_id),
            )
            await conn.execute(
                "UPDATE resume_compositions SET profile_variant_id=%s WHERE id=%s",
                (created["id"], cid),
            )
        saved = await rerender(conn, user_id, cid, f"profile-save-{mode}")
        return saved, None


async def detach_variant(conn, user_id, variant_id):
    async with conn.transaction():
        variant = await one(
            conn,
            """SELECT v.*, b.parent_id, b.section FROM bullet_variants v
               JOIN bullets b ON b.id=v.bullet_id
               WHERE v.id=%s AND v.user_id=%s AND v.archived_at IS NULL""",
            (variant_id, user_id),
        )
        if not variant:
            return None
        bullet = await _insert_sibling_bullet(conn, user_id, variant["bullet_id"])
        await conn.execute(
            """UPDATE bullet_variants SET bullet_id=%s,is_default=true,sort_order=0,updated_at=now()
               WHERE id=%s""",
            (bullet["id"], variant_id),
        )
        await conn.execute(
            "UPDATE bullet_variants SET is_default=false,updated_at=now() WHERE bullet_id=%s AND id<>%s",
            (variant["bullet_id"], variant_id),
        )
        remaining = await one(
            conn,
            """SELECT id FROM bullet_variants WHERE bullet_id=%s AND user_id=%s AND archived_at IS NULL AND is_default
               LIMIT 1""",
            (variant["bullet_id"], user_id),
        )
        if not remaining:
            fallback = await one(
                conn,
                """SELECT id FROM bullet_variants WHERE bullet_id=%s AND user_id=%s AND archived_at IS NULL
                   ORDER BY sort_order,id LIMIT 1""",
                (variant["bullet_id"], user_id),
            )
            if fallback:
                await conn.execute(
                    "UPDATE bullet_variants SET is_default=true,updated_at=now() WHERE id=%s",
                    (fallback["id"],),
                )
        await conn.execute(
            "UPDATE composition_bullets SET bullet_id=%s,updated_at=now() WHERE variant_id=%s",
            (bullet["id"], variant_id),
        )
        return {"id": str(bullet["id"]), "variant_id": str(variant_id)}


async def attach_bullet(conn, user_id, bullet_id, target_id):
    async with conn.transaction():
        if str(bullet_id) == str(target_id):
            return None, "same"
        source = await one(
            conn,
            "SELECT id,parent_id FROM bullets WHERE id=%s AND user_id=%s AND archived_at IS NULL",
            (bullet_id, user_id),
        )
        target = await one(
            conn,
            "SELECT id FROM bullets WHERE id=%s AND user_id=%s AND archived_at IS NULL",
            (target_id, user_id),
        )
        if not source or not target:
            return None, "missing"
        variants = await many(
            conn,
            "SELECT id,name FROM bullet_variants WHERE bullet_id=%s AND user_id=%s ORDER BY sort_order,id",
            (bullet_id, user_id),
        )
        for variant in variants:
            name = await _unique_name(
                conn,
                "SELECT id FROM bullet_variants WHERE bullet_id=%s AND id<>%s AND name=%s",
                (target_id, variant["id"]),
                variant["name"],
            )
            await conn.execute(
                """UPDATE bullet_variants SET bullet_id=%s,name=%s,is_default=false,updated_at=now()
                   WHERE id=%s""",
                (target_id, name, variant["id"]),
            )
        placements = await many(
            conn,
            "SELECT id,composition_id FROM composition_bullets WHERE bullet_id=%s",
            (bullet_id,),
        )
        for placement in placements:
            clash = await one(
                conn,
                "SELECT id FROM composition_bullets WHERE composition_id=%s AND bullet_id=%s",
                (placement["composition_id"], target_id),
            )
            if clash:
                await conn.execute("DELETE FROM composition_bullets WHERE id=%s", (placement["id"],))
            else:
                await conn.execute(
                    "UPDATE composition_bullets SET bullet_id=%s,updated_at=now() WHERE id=%s",
                    (target_id, placement["id"]),
                )
        kept = await one(
            conn,
            """SELECT id FROM bullet_variants
               WHERE bullet_id=%s AND user_id=%s AND archived_at IS NULL AND is_default LIMIT 1""",
            (target_id, user_id),
        )
        if not kept and variants:
            await conn.execute(
                "UPDATE bullet_variants SET is_default=true,updated_at=now() WHERE id=%s",
                (variants[0]["id"],),
            )
        await conn.execute(
            "UPDATE bullets SET archived_at=now(),updated_at=now() WHERE id=%s AND user_id=%s",
            (bullet_id, user_id),
        )
        return {"id": str(target_id)}, None
