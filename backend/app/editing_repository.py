





import json
from psycopg.rows import dict_row


async def one(conn, sql, params=()):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        return await cur.fetchone()


def historical_date(row):
    if row.get("date_label"):
        return row["date_label"]
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

    def part(year, month):
        if not year:
            return ""
        return f"{names[month]} {year}" if month else str(year)

    start = part(row.get("start_year"), row.get("start_month"))
    end = (
        "Present"
        if row.get("is_current")
        else part(row.get("end_year"), row.get("end_month"))
    )
    return " - ".join(x for x in (start, end) if x)


async def render_historical(conn, user_id, item_id, composition_id=None):
    row = await one(
        conn,
        "SELECT * FROM content_items WHERE id=%s AND user_id=%s",
        (item_id, user_id),
    )
    if not row:
        return None
    rows = [] if composition_id else await many(
            conn,
            """SELECT b.id,v.body FROM bullets b JOIN LATERAL (SELECT body FROM bullet_variants x WHERE x.bullet_id=b.id AND x.user_id=b.user_id AND x.archived_at IS NULL ORDER BY x.is_default DESC,x.sort_order,x.id LIMIT 1) v ON true WHERE b.parent_id=%s AND b.user_id=%s AND b.archived_at IS NULL ORDER BY b.sort_order,b.id""",
            (item_id, user_id),
        )
    base = {"id": str(row["id"]), "date": row.get("date_label") or "", "date_label": row.get("date_label") or "", "start_year": row.get("start_year"), "start_month": row.get("start_month"), "end_year": row.get("end_year"), "end_month": row.get("end_month"), "is_current": row.get("is_current", False), "manual_order": row.get("sort_order", 0), "bullets": [x["body"] for x in rows]}
    if row["kind"] == "project":
        base.update(name=row["name"], subtitle=row.get("subtitle") or "")
    else:
        base.update(
            organization=row["organization"],
            location=row.get("location") or "",
            title=row["title"],
        )
    return base


async def refresh_historical_compositions(conn, user_id, item_id, source):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """SELECT c.id,c.render_payload FROM resume_compositions c JOIN composition_items i ON i.composition_id=c.id WHERE c.user_id=%s AND i.item_id=%s AND i.section IN ('projects','work_experience','leadership') FOR UPDATE""",
            (user_id, item_id),
        )
        comps = await cur.fetchall()
    for comp in comps:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """SELECT i.section,x.id FROM composition_items i JOIN content_items x ON x.id=i.item_id WHERE i.composition_id=%s AND i.section IN ('projects','work_experience','leadership') ORDER BY i.section,i.sort_order,i.id""",
                (comp["id"],),
            )
            selected = await cur.fetchall()
        resume = comp["render_payload"]
        for section in ("projects", "work_experience", "leadership"):
            resume[section] = [
                await render_historical(conn, user_id, x["id"], comp["id"])
                for x in selected
                if x["section"] == section
            ]
        row = await one(
            conn,
            "UPDATE resume_compositions SET render_payload=%s::jsonb,revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s RETURNING revision",
            (json.dumps(resume), comp["id"], user_id),
        )
        await conn.execute(
            "INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,%s,%s::jsonb)",
            (
                comp["id"],
                user_id,
                row["revision"],
                source,
                json.dumps({"resume": resume}),
            ),
        )


async def add_item(conn, user_id, payload):
    async with conn.transaction():
        row = await one(
            conn,
            """INSERT INTO content_items(user_id,kind,name,subtitle,organization,location,title,date_label,start_year,start_month,end_year,end_month,is_current,sort_order) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM content_items WHERE user_id=%s AND kind=%s)) RETURNING id""",
            (
                user_id,
                payload.kind,
                payload.name,
                payload.subtitle,
                payload.organization,
                payload.location,
                payload.title,
                payload.date_label.strip(),
                payload.start_year,
                payload.start_month,
                payload.end_year,
                payload.end_month,
                payload.is_current,
                user_id,
                payload.kind,
            ),
        )
        for i, body in enumerate(payload.bullets):
            if not body.strip():
                continue
            b = await one(
                conn,
                "INSERT INTO bullets(user_id,parent_id,sort_order) VALUES(%s,%s,%s) RETURNING id",
                (user_id, row["id"], i),
            )
            await conn.execute(
                "INSERT INTO bullet_variants(user_id,bullet_id,name,body,is_default,sort_order) VALUES(%s,%s,'Default',%s,true,0)",
                (user_id, b["id"], body.strip()),
            )
        return row["id"]


async def update_item(conn, user_id, item_id, payload):
    async with conn.transaction():
        row = await one(
            conn,
            """UPDATE content_items SET name=%s,subtitle=%s,organization=%s,location=%s,title=%s,date_label=%s,start_year=%s,start_month=%s,end_year=%s,end_month=%s,is_current=%s,updated_at=now() WHERE id=%s AND user_id=%s AND kind=%s AND archived_at IS NULL RETURNING id""",
            (
                payload.name,
                payload.subtitle,
                payload.organization,
                payload.location,
                payload.title,
                payload.date_label.strip(),
                payload.start_year,
                payload.start_month,
                payload.end_year,
                payload.end_month,
                payload.is_current,
                item_id,
                user_id,
                payload.kind,
            ),
        )
        if row:
            await refresh_historical_compositions(
                conn, user_id, item_id, "historical-library-update"
            )
        return row and row["id"]


async def reorder_items(conn, user_id, kind, ids):
    async with conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id FROM content_items WHERE user_id=%s AND kind=%s AND id=ANY(%s)",
                (user_id, kind, ids),
            )
            owned = await cur.fetchall()
        if {x["id"] for x in owned} != set(ids):
            return False
        for i, rid in enumerate(ids):
            await conn.execute(
                "UPDATE content_items SET sort_order=%s,updated_at=now() WHERE id=%s AND user_id=%s AND kind=%s",
                (i, rid, user_id, kind),
            )
    return True


async def select_historical(conn, user_id, cid, revision, section, item_id, included):
    kinds = {
        "projects": "project",
        "work_experience": "employment",
        "leadership": "leadership",
    }
    kind = kinds.get(section)
    if not kind:
        return None, "missing"
    async with conn.transaction():
        item = await one(
            conn,
            "SELECT id,archived_at FROM content_items WHERE id=%s AND user_id=%s AND kind=%s",
            (item_id, user_id, kind),
        )
        if not item or (included and item["archived_at"]):
            return None, "missing"
        locked = await one(
            conn,
            "SELECT id,render_payload FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s FOR UPDATE",
            (cid, user_id, revision),
        )
        if not locked:
            return None, (
                "stale"
                if await one(
                    conn,
                    "SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",
                    (cid, user_id),
                )
                else "missing"
            )
        if included:
            await conn.execute(
                "INSERT INTO composition_items(composition_id,section,item_id,sort_order) VALUES(%s,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM composition_items WHERE composition_id=%s AND section=%s)) ON CONFLICT DO NOTHING",
                (cid, section, item_id, cid, section),
            )
        else:
            await conn.execute(
                "DELETE FROM composition_items WHERE composition_id=%s AND section=%s AND item_id=%s",
                (cid, section, item_id),
            )
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT item_id FROM composition_items WHERE composition_id=%s AND section=%s ORDER BY sort_order,id",
                (cid, section),
            )
            selected = await cur.fetchall()
        resume = locked["render_payload"]
        resume[section] = [
            await render_historical(conn, user_id, x["item_id"], cid) for x in selected
        ]
        row = await one(
            conn,
            "UPDATE resume_compositions SET render_payload=%s::jsonb,revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s RETURNING *",
            (json.dumps(resume), cid, user_id),
        )
        await conn.execute(
            "INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,'historical-selection',%s::jsonb)",
            (cid, user_id, row["revision"], json.dumps({"resume": resume})),
        )
        return row, None


async def save_composition(conn, user_id, cid, revision, resume, source="autosave"):
    snapshot = {"resume": resume}
    async with conn.transaction():
        row = await one(
            conn,
            "UPDATE resume_compositions SET render_payload=%s::jsonb,revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s RETURNING *",
            (json.dumps(resume), cid, user_id, revision),
        )
        if row:
            await conn.execute(
                "INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,%s,%s::jsonb)",
                (cid, user_id, row["revision"], source, json.dumps(snapshot)),
            )
        return row


async def create_composition(
    conn,
    user_id,
    name,
    description,
    resume,
    *,
    display_name=None,
    display_title="",
    target_company="",
    target_role="",
):
    async with conn.transaction():
        if name:
            internal_name = name.strip()
        else:
            # Serialize automatic naming per user so concurrent requests cannot choose the same suffix.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(user_id),))
            base = f"{(display_name or 'User').strip() or 'User'}'s Resume ({__import__('datetime').date.today().strftime('%m/%d/%Y')})"
            existing = await many(
                conn,
                "SELECT name FROM resume_compositions WHERE user_id=%s AND (name=%s OR name LIKE %s)",
                (user_id, base, base + " (%)"),
            )
            used = {row["name"] for row in existing}
            internal_name = base
            suffix = 2
            while internal_name in used:
                internal_name = f"{base} ({suffix})"
                suffix += 1
        row = await one(
            conn,
            """INSERT INTO resume_compositions(
                user_id,name,description,display_title,target_company,target_role,render_payload
            ) VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb)
            RETURNING id,name,description,display_title,target_company,target_role,
                summary_variant_id,revision,render_payload,interest_layout,section_order,
                preferred_page_length,date_format,section_sort_modes,
                archived_at,created_at,updated_at,autosaved_at""",
            (
                user_id,
                internal_name,
                description.strip(),
                display_title.strip(),
                target_company.strip(),
                target_role.strip(),
                resume.model_dump_json(),
            ),
        )
        await conn.execute(
            """INSERT INTO composition_revisions(
                composition_id,user_id,revision,source,snapshot
            ) VALUES(%s,%s,%s,'create',%s::jsonb)""",
            (
                row["id"],
                user_id,
                row["revision"],
                json.dumps({
                    "name": row["name"],
                    "description": row["description"],
                    "display_title": row["display_title"],
                    "target_company": row["target_company"],
                    "target_role": row["target_role"],
                    "resume": row["render_payload"],
                    "interest_layout": row["interest_layout"],
                    "section_order": row["section_order"],
                }),
            ),
        )
        return row

async def update_composition_metadata(
    conn,user_id,cid,revision,name,description,display_title="",target_company="",target_role=""
):
    async with conn.transaction():
        row = await one(
            conn,
            """
            UPDATE resume_compositions 
            SET
                name=%s,
                description=%s,
                display_title=%s,
                target_company=%s,
                target_role=%s,
                revision=revision+1,
                updated_at=now()
            WHERE 
                id=%s 
                AND user_id=%s 
                AND revision=%s
            RETURNING *""",
            (
                name.strip(),description.strip(),display_title.strip(),target_company.strip(),
                target_role.strip(),cid,user_id,revision,
            ),
        )
        if not row:
            exists = await one(conn,"SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",(cid,user_id))
            return None, "stale" if exists else "missing"
        await conn.execute(
            "INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,'metadata',%s::jsonb)",
            (cid,user_id,row["revision"],json.dumps({
                "name":row["name"],"description":row["description"],
                "display_title":row["display_title"],"target_company":row["target_company"],
                "target_role":row["target_role"],"resume":row["render_payload"],
                "interest_layout":row["interest_layout"],"section_order":row["section_order"],
            })),
        )
        return row,None

async def set_composition_archive(conn,user_id,cid,revision,archived):
    async with conn.transaction():
        clause='archived_at IS NULL' if archived else 'archived_at IS NOT NULL'
        row=await one(conn,f"""UPDATE resume_compositions SET archived_at={'now()' if archived else 'NULL'},revision=revision+1,updated_at=now()
            WHERE id=%s AND user_id=%s AND {clause} AND revision=%s
            RETURNING *
                revision,render_payload,interest_layout,section_order,archived_at,created_at,updated_at,autosaved_at""",(cid,user_id,revision))
        if not row:return None,('stale' if await one(conn,"SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s",(cid,user_id)) else 'missing')
        await conn.execute("INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,%s,%s::jsonb)",(cid,user_id,row['revision'],'archive' if archived else 'restore-composition',json.dumps({'name':row['name'],'description':row['description'],'display_title':row['display_title'],'target_company':row['target_company'],'target_role':row['target_role'],'preferred_page_length':row.get('preferred_page_length',1),'date_format':row.get('date_format','long'),'section_sort_modes':row.get('section_sort_modes',{}),'resume':row['render_payload'],'interest_layout':row['interest_layout'],'section_order':row['section_order']})))
        return row,None

async def duplicate(conn, user_id, cid, name):
    async with conn.transaction():
        row = await one(conn,"""INSERT INTO resume_compositions(
            user_id,name,description,display_title,target_company,target_role,tags,summary_variant_id,render_payload,interest_layout,section_order,preferred_page_length,date_format,section_sort_modes
        ) SELECT user_id,%s,description,display_title,target_company,target_role,tags,summary_variant_id,render_payload,interest_layout,section_order,preferred_page_length,date_format,section_sort_modes
        FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL
        RETURNING *""",(name.strip(),cid,user_id))
        if row:
            await conn.execute("INSERT INTO composition_items(composition_id,section,item_id,sort_order) SELECT %s,section,item_id,sort_order FROM composition_items WHERE composition_id=%s",(row['id'],cid))
            await conn.execute("INSERT INTO composition_bullets(composition_id,bullet_id,variant_id,destination_section,destination_parent_type,destination_parent_id,sort_order,wording_snapshot,snapshot_source_updated_at) SELECT %s,bullet_id,variant_id,destination_section,destination_parent_type,destination_parent_id,sort_order,wording_snapshot,snapshot_source_updated_at FROM composition_bullets WHERE composition_id=%s",(row['id'],cid))
            await conn.execute("INSERT INTO composition_custom_sections(composition_id,section_id,sort_order) SELECT %s,section_id,sort_order FROM composition_custom_sections WHERE composition_id=%s",(row['id'],cid))
            await conn.execute("INSERT INTO composition_revisions(composition_id,user_id,revision,source,note,snapshot) VALUES(%s,%s,%s,'duplicate',%s,%s::jsonb)",(row['id'],user_id,row['revision'],f"Duplicated from {cid}",json.dumps({'name':row['name'],'description':row['description'],'display_title':row['display_title'],'target_company':row['target_company'],'target_role':row['target_role'],'preferred_page_length':row.get('preferred_page_length',1),'date_format':row.get('date_format','long'),'section_sort_modes':row.get('section_sort_modes',{}),'resume':row['render_payload'],'interest_layout':row['interest_layout'],'section_order':row['section_order']})))
        return row

async def list_revisions(conn, user_id, cid):
    async with conn.cursor(row_factory=dict_row) as c:
        await c.execute(
            "SELECT r.id,r.revision,r.source,r.note,r.created_at FROM composition_revisions r JOIN resume_compositions x ON x.id=r.composition_id WHERE r.composition_id=%s AND r.user_id=%s AND x.user_id=%s ORDER BY r.revision DESC",
            (cid, user_id, user_id),
        )
        return await c.fetchall()


async def get_revision(conn, user_id, cid, rid):
    return await one(
        conn,
        "SELECT r.id,r.revision,r.source,r.note,r.snapshot,r.created_at FROM composition_revisions r JOIN resume_compositions x ON x.id=r.composition_id WHERE r.id=%s AND r.composition_id=%s AND r.user_id=%s AND x.user_id=%s",
        (rid, cid, user_id, user_id),
    )


async def revision_snapshot(conn, row):
    items = await many(conn, "SELECT section,item_id,sort_order FROM composition_items WHERE composition_id=%s ORDER BY section,sort_order,id", (row["id"],))
    custom = await many(conn, "SELECT section_id,sort_order FROM composition_custom_sections WHERE composition_id=%s ORDER BY sort_order,id", (row["id"],))
    placements = await many(conn, "SELECT bullet_id,variant_id,destination_section,destination_parent_type,destination_parent_id,sort_order,wording_snapshot,snapshot_source_updated_at FROM composition_bullets WHERE composition_id=%s ORDER BY destination_section,destination_parent_id,sort_order,id", (row["id"],))
    return {"name":row["name"],"description":row.get("description", ""),"display_title":row.get("display_title", ""),"target_company":row.get("target_company", ""),"target_role":row.get("target_role", ""),"resume":row["render_payload"],"preferred_page_length":row.get("preferred_page_length",1),"date_format":row.get("date_format","long"),"section_sort_modes":row.get("section_sort_modes",{}),"section_order":row.get("section_order",[]),"interest_layout":row.get("interest_layout","compact"),"summary_variant_id":str(row["summary_variant_id"]) if row.get("summary_variant_id") else None,"composition_items":[{**x,"item_id":str(x["item_id"])} for x in items],"composition_custom_sections":[{**x,"section_id":str(x["section_id"])} for x in custom],"bullet_placements":[{k:(str(v) if k.endswith("_id") and v is not None else v) for k,v in x.items()} for x in placements]}

async def restore_revision(conn, user_id, cid, rid, expected):
    async with conn.transaction():
        old=await get_revision(conn,user_id,cid,rid)
        if not old:return None,"missing"
        current=await one(conn,"SELECT * FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL FOR UPDATE",(cid,user_id))
        if not current:return None,"missing"
        if current["revision"]!=expected:return None,"stale"
        snap=old["snapshot"] or {}; name=snap.get("name",current["name"])
        duplicate_name=await one(conn,"SELECT id FROM resume_compositions WHERE user_id=%s AND archived_at IS NULL AND name=%s AND id<>%s",(user_id,name,cid))
        if duplicate_name:return None,"name-conflict"
        value=lambda key:snap[key] if key in snap else current.get(key)
        row=await one(conn,"""UPDATE resume_compositions SET name=%s,description=%s,display_title=%s,target_company=%s,target_role=%s,render_payload=%s::jsonb,preferred_page_length=%s,date_format=%s,section_sort_modes=%s::jsonb,section_order=%s::jsonb,interest_layout=%s,summary_variant_id=%s,revision=revision+1,updated_at=now(),autosaved_at=now() WHERE id=%s AND user_id=%s RETURNING *""",(name,value("description"),value("display_title"),value("target_company"),value("target_role"),json.dumps(snap.get("resume",current["render_payload"])),value("preferred_page_length"),value("date_format"),json.dumps(value("section_sort_modes") or {}),json.dumps(value("section_order") or []),value("interest_layout"),value("summary_variant_id"),cid,user_id))
        if "composition_items" in snap:
            await conn.execute("DELETE FROM composition_items WHERE composition_id=%s",(cid,))
            for x in snap["composition_items"]: await conn.execute("INSERT INTO composition_items(composition_id,section,item_id,sort_order) VALUES(%s,%s,%s,%s)",(cid,x["section"],x["item_id"],x.get("sort_order",0)))
        if "composition_custom_sections" in snap:
            await conn.execute("DELETE FROM composition_custom_sections WHERE composition_id=%s",(cid,))
            for x in snap["composition_custom_sections"]: await conn.execute("INSERT INTO composition_custom_sections(composition_id,section_id,sort_order) VALUES(%s,%s,%s)",(cid,x["section_id"],x.get("sort_order",0)))
        if "bullet_placements" in snap:
            await conn.execute("DELETE FROM composition_bullets WHERE composition_id=%s",(cid,))
            for x in snap["bullet_placements"]: await conn.execute("INSERT INTO composition_bullets(composition_id,bullet_id,variant_id,destination_section,destination_parent_type,destination_parent_id,sort_order,wording_snapshot,snapshot_source_updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",(cid,x["bullet_id"],x["variant_id"],x.get("destination_section"),x.get("destination_parent_type"),x.get("destination_parent_id"),x.get("sort_order",0),x.get("wording_snapshot",""),x.get("snapshot_source_updated_at")))
        snap2=await revision_snapshot(conn,row)
        await conn.execute("INSERT INTO composition_revisions(composition_id,user_id,revision,source,note,snapshot) VALUES(%s,%s,%s,'restore',%s,%s::jsonb)",(cid,user_id,row["revision"],f"Restored revision {old['revision']}",json.dumps(snap2,default=str)))
        return row,None

async def many(conn, sql, params=()):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        return await cur.fetchall()


async def _parent(conn, user_id, parent_id, active=True):
    return await one(
        conn,
        "SELECT id,kind,archived_at FROM content_items WHERE id=%s AND user_id=%s"
        + (" AND archived_at IS NULL" if active else ""),
        (parent_id, user_id),
    )


async def _bullet(conn, user_id, bullet_id, active=True):
    return await one(
        conn,
        "SELECT b.id,b.parent_id,b.archived_at,x.kind,x.archived_at parent_archived FROM bullets b JOIN content_items x ON x.id=b.parent_id AND x.user_id=b.user_id WHERE b.id=%s AND b.user_id=%s"
        + (" AND b.archived_at IS NULL AND x.archived_at IS NULL" if active else ""),
        (bullet_id, user_id),
    )


async def _variant(conn, user_id, variant_id, active=True):
    return await one(
        conn,
        "SELECT v.id,v.bullet_id,v.is_default,v.archived_at,b.parent_id,b.archived_at bullet_archived,x.archived_at parent_archived FROM bullet_variants v JOIN bullets b ON b.id=v.bullet_id AND b.user_id=v.user_id JOIN content_items x ON x.id=b.parent_id AND x.user_id=b.user_id WHERE v.id=%s AND v.user_id=%s"
        + (
            " AND v.archived_at IS NULL AND b.archived_at IS NULL AND x.archived_at IS NULL"
            if active
            else ""
        ),
        (variant_id, user_id),
    )


async def _ensure_default(conn, user_id, bullet_id):
    active = await many(
        conn,
        "SELECT id,is_default FROM bullet_variants WHERE bullet_id=%s AND user_id=%s AND archived_at IS NULL ORDER BY is_default DESC,sort_order,id FOR UPDATE",
        (bullet_id, user_id),
    )
    if active and not any(x["is_default"] for x in active):
        await conn.execute(
            "UPDATE bullet_variants SET is_default=true,updated_at=now() WHERE id=%s AND user_id=%s",
            (active[0]["id"], user_id),
        )


async def _refresh_parents(conn, user_id, parent_ids, source):
    ids = list(dict.fromkeys(parent_ids))
    if not ids:
        return
    comps = await many(
        conn,
        """SELECT c.id,c.render_payload FROM resume_compositions c WHERE c.user_id=%s AND c.archived_at IS NULL AND EXISTS (SELECT 1 FROM composition_items i WHERE i.composition_id=c.id AND i.item_id=ANY(%s) AND i.section IN ('projects','work_experience','leadership')) FOR UPDATE""",
        (user_id, ids),
    )
    for comp in comps:
        selected = await many(
            conn,
            """SELECT i.section,x.id FROM composition_items i JOIN content_items x ON x.id=i.item_id WHERE i.composition_id=%s AND i.section IN ('projects','work_experience','leadership') ORDER BY i.section,i.sort_order,i.id""",
            (comp["id"],),
        )
        resume = comp["render_payload"]
        for section in ("projects", "work_experience", "leadership"):
            resume[section] = [
                await render_historical(conn, user_id, x["id"], comp["id"])
                for x in selected
                if x["section"] == section
            ]
        row = await one(
            conn,
            "UPDATE resume_compositions SET render_payload=%s::jsonb,revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s RETURNING revision",
            (json.dumps(resume), comp["id"], user_id),
        )
        await conn.execute(
            "INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,%s,%s::jsonb)",
            (
                comp["id"],
                user_id,
                row["revision"],
                source,
                json.dumps({"resume": resume}),
            ),
        )


async def create_bullet(conn, user_id, payload):
    async with conn.transaction():
        if not await _parent(conn, user_id, payload.parent_id):
            return None
        bullet = await one(
            conn,
            "INSERT INTO bullets(user_id,parent_id,sort_order) VALUES(%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM bullets WHERE parent_id=%s)) RETURNING id",
            (user_id, payload.parent_id, payload.parent_id),
        )
        variant = await one(
            conn,
            "INSERT INTO bullet_variants(user_id,bullet_id,name,body,is_default,sort_order) VALUES(%s,%s,%s,%s,true,0) RETURNING id",
            (user_id, bullet["id"], payload.variant_name.strip(), payload.body.strip()),
        )
        await _refresh_parents(conn, user_id, [payload.parent_id], "bullet-create")
        return {"id": bullet["id"], "variant_id": variant["id"]}


async def reorder_bullets(conn, user_id, parent_id, ids):
    async with conn.transaction():
        if not await _parent(conn, user_id, parent_id):
            return False
        siblings = await many(
            conn,
            "SELECT id FROM bullets WHERE parent_id=%s AND user_id=%s ORDER BY sort_order,id FOR UPDATE",
            (parent_id, user_id),
        )
        if [x["id"] for x in siblings] != list(ids) and {
            x["id"] for x in siblings
        } != set(ids):
            return False
        for index, rid in enumerate(ids):
            await conn.execute(
                "UPDATE bullets SET sort_order=%s,updated_at=now() WHERE id=%s AND user_id=%s AND parent_id=%s",
                (index, rid, user_id, parent_id),
            )
        await _refresh_parents(conn, user_id, [parent_id], "bullet-reorder")
        return True


async def move_bullet(conn, user_id, bullet_id, destination_id):
    async with conn.transaction():
        bullet = await _bullet(conn, user_id, bullet_id)
        destination = await _parent(conn, user_id, destination_id)
        if not bullet or not destination:
            return None
        source = bullet["parent_id"]
        await conn.execute(
            "UPDATE bullets SET parent_id=%s,sort_order=(SELECT COALESCE(max(sort_order)+1,0) FROM bullets WHERE parent_id=%s),updated_at=now() WHERE id=%s AND user_id=%s",
            (destination_id, destination_id, bullet_id, user_id),
        )
        await _refresh_parents(conn, user_id, [source, destination_id], "bullet-move")
        return {"id": bullet_id}


async def duplicate_bullet(conn, user_id, bullet_id):
    async with conn.transaction():
        bullet = await _bullet(conn, user_id, bullet_id, False)
        if not bullet:
            return None
        copy = await one(
            conn,
            "INSERT INTO bullets(user_id,parent_id,sort_order,archived_at) SELECT user_id,parent_id,(SELECT COALESCE(max(sort_order)+1,0) FROM bullets WHERE parent_id=%s),archived_at FROM bullets WHERE id=%s AND user_id=%s RETURNING id,parent_id",
            (bullet["parent_id"], bullet_id, user_id),
        )
        await conn.execute(
            "INSERT INTO bullet_variants(user_id,bullet_id,name,body,is_default,sort_order,archived_at) SELECT user_id,%s,name,body,is_default,sort_order,archived_at FROM bullet_variants WHERE bullet_id=%s AND user_id=%s ORDER BY sort_order,id",
            (copy["id"], bullet_id, user_id),
        )
        await _refresh_parents(conn, user_id, [copy["parent_id"]], "bullet-duplicate")
        return {"id": copy["id"]}


async def archive_bullet(conn, user_id, bullet_id):
    async with conn.transaction():
        bullet = await _bullet(conn, user_id, bullet_id, False)
        if not bullet:
            return None
        await conn.execute(
            "UPDATE bullets SET archived_at=now(),updated_at=now() WHERE id=%s AND user_id=%s",
            (bullet_id, user_id),
        )
        await _refresh_parents(conn, user_id, [bullet["parent_id"]], "bullet-archive")
        return {"id": bullet_id}


async def restore_bullet(conn, user_id, bullet_id, parent_id=None):
    async with conn.transaction():
        bullet = await _bullet(conn, user_id, bullet_id, False)
        if not bullet or not bullet["archived_at"]:
            return None, "missing"
        target = parent_id or bullet["parent_id"]
        if not await _parent(conn, user_id, target):
            return None, "parent"
        await conn.execute(
            "UPDATE bullets SET archived_at=NULL,parent_id=%s,sort_order=(SELECT COALESCE(max(sort_order)+1,0) FROM bullets WHERE parent_id=%s),updated_at=now() WHERE id=%s AND user_id=%s",
            (target, target, bullet_id, user_id),
        )
        await _ensure_default(conn, user_id, bullet_id)
        await _refresh_parents(
            conn, user_id, [bullet["parent_id"], target], "bullet-restore"
        )
        return {"id": bullet_id}, None


async def create_variant(conn, user_id, bullet_id, payload):
    async with conn.transaction():
        bullet = await _bullet(conn, user_id, bullet_id)
        if not bullet:
            return None
        has = await one(
            conn,
            "SELECT id FROM bullet_variants WHERE bullet_id=%s AND user_id=%s AND archived_at IS NULL LIMIT 1",
            (bullet_id, user_id),
        )
        row = await one(
            conn,
            "INSERT INTO bullet_variants(user_id,bullet_id,name,body,is_default,sort_order) VALUES(%s,%s,%s,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM bullet_variants WHERE bullet_id=%s)) RETURNING id",
            (
                user_id,
                bullet_id,
                payload.name.strip(),
                payload.body.strip(),
                not bool(has),
                bullet_id,
            ),
        )
        await _refresh_parents(conn, user_id, [bullet["parent_id"]], "variant-create")
        return row


async def update_variant(conn, user_id, variant_id, payload):
    async with conn.transaction():
        variant = await _variant(conn, user_id, variant_id, False)
        if not variant:
            return None
        row = await one(
            conn,
            "UPDATE bullet_variants SET name=%s,body=%s,updated_at=now() WHERE id=%s AND user_id=%s RETURNING id",
            (payload.name.strip(), payload.body.strip(), variant_id, user_id),
        )
        # Phase 2J wording preservation: existing resume snapshots remain unchanged.
        return row


async def reorder_variants(conn, user_id, bullet_id, ids):
    async with conn.transaction():
        bullet = await _bullet(conn, user_id, bullet_id, False)
        if not bullet:
            return False
        siblings = await many(
            conn,
            "SELECT id FROM bullet_variants WHERE bullet_id=%s AND user_id=%s ORDER BY sort_order,id FOR UPDATE",
            (bullet_id, user_id),
        )
        if {x["id"] for x in siblings} != set(ids):
            return False
        for index, rid in enumerate(ids):
            await conn.execute(
                "UPDATE bullet_variants SET sort_order=%s,updated_at=now() WHERE id=%s AND user_id=%s AND bullet_id=%s",
                (index, rid, user_id, bullet_id),
            )
        await _refresh_parents(conn, user_id, [bullet["parent_id"]], "variant-reorder")
        return True


async def duplicate_variant(conn, user_id, variant_id):
    async with conn.transaction():
        variant = await _variant(conn, user_id, variant_id, False)
        if not variant:
            return None
        base = await one(
            conn,
            "SELECT name,body,sort_order FROM bullet_variants WHERE id=%s AND user_id=%s",
            (variant_id, user_id),
        )
        name = base["name"] + " Copy"
        counter = 2
        while await one(
            conn,
            "SELECT id FROM bullet_variants WHERE bullet_id=%s AND name=%s",
            (variant["bullet_id"], name),
        ):
            name = f"{base['name']} Copy {counter}"
            counter += 1
        row = await one(
            conn,
            "INSERT INTO bullet_variants(user_id,bullet_id,name,body,is_default,sort_order) VALUES(%s,%s,%s,%s,false,(SELECT COALESCE(max(sort_order)+1,0) FROM bullet_variants WHERE bullet_id=%s)) RETURNING id",
            (user_id, variant["bullet_id"], name, base["body"], variant["bullet_id"]),
        )
        await _ensure_default(conn, user_id, variant["bullet_id"])
        await _refresh_parents(
            conn, user_id, [variant["parent_id"]], "variant-duplicate"
        )
        return row


async def set_default_variant(conn, user_id, variant_id):
    async with conn.transaction():
        variant = await _variant(conn, user_id, variant_id)
        if not variant:
            return None
        await conn.execute(
            "UPDATE bullet_variants SET is_default=false,updated_at=now() WHERE bullet_id=%s AND user_id=%s AND archived_at IS NULL",
            (variant["bullet_id"], user_id),
        )
        await conn.execute(
            "UPDATE bullet_variants SET is_default=true,updated_at=now() WHERE id=%s AND user_id=%s",
            (variant_id, user_id),
        )
        await _refresh_parents(conn, user_id, [variant["parent_id"]], "variant-default")
        return {"id": variant_id}


async def archive_variant(conn, user_id, variant_id, replacement_id=None):
    async with conn.transaction():
        variant = await _variant(conn, user_id, variant_id, False)
        if not variant:
            return None, "missing"
        active = await many(
            conn,
            "SELECT id,is_default FROM bullet_variants WHERE bullet_id=%s AND user_id=%s AND archived_at IS NULL AND id<>%s ORDER BY sort_order,id FOR UPDATE",
            (variant["bullet_id"], user_id, variant_id),
        )
        if not active:
            return None, "last-active"
        if variant["is_default"] and active:
            replacement = None
            if replacement_id:
                replacement = next(
                    (x for x in active if x["id"] == replacement_id), None
                )
            if not replacement:
                return None, "replacement"
            await conn.execute(
                "UPDATE bullet_variants SET is_default=false,updated_at=now() WHERE id=%s AND user_id=%s",
                (variant_id, user_id),
            )
            await conn.execute(
                "UPDATE bullet_variants SET is_default=true,updated_at=now() WHERE id=%s AND user_id=%s",
                (replacement_id, user_id),
            )
        await conn.execute(
            "UPDATE bullet_variants SET archived_at=now(),is_default=false,updated_at=now() WHERE id=%s AND user_id=%s",
            (variant_id, user_id),
        )
        await _refresh_parents(conn, user_id, [variant["parent_id"]], "variant-archive")
        return {"id": variant_id}, None


async def restore_variant(conn, user_id, variant_id):
    async with conn.transaction():
        variant = await _variant(conn, user_id, variant_id, False)
        if (
            not variant
            or not variant["archived_at"]
            or variant["bullet_archived"]
            or variant["parent_archived"]
        ):
            return None
        await conn.execute(
            "UPDATE bullet_variants SET archived_at=NULL,is_default=false,updated_at=now() WHERE id=%s AND user_id=%s",
            (variant_id, user_id),
        )
        await _ensure_default(conn, user_id, variant["bullet_id"])
        await _refresh_parents(conn, user_id, [variant["parent_id"]], "variant-restore")
        return {"id": variant_id}


