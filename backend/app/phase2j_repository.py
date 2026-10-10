


import json
from psycopg.rows import dict_row

async def _one(conn, sql, params=()):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        return await cur.fetchone()

async def _many(conn, sql, params=()):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        return await cur.fetchall()

async def _lock_composition(conn,user_id,cid,revision):
    row=await _one(conn,"SELECT * FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s FOR UPDATE",(cid,user_id,revision))
    if row:return row,None
    exists=await _one(conn,"SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",(cid,user_id))
    return None,"stale" if exists else "missing"

async def _destination(conn,user_id,parent_type,parent_id,active=True):
    tables={"content_item":"content_items","education_item":"education_items","tool_group":"tool_groups","interest":"interests","custom_entry":"custom_section_entries"}
    table=tables.get(parent_type)
    if not table:return None
    return await _one(conn,f"SELECT id FROM {table} WHERE id=%s AND user_id=%s"+(" AND archived_at IS NULL" if active else ""),(parent_id,user_id))

async def _bullet_variant(conn,user_id,bullet_id,variant_id,active=True):
    clause=" AND b.archived_at IS NULL AND v.archived_at IS NULL" if active else ""
    return await _one(conn,"SELECT b.id bullet_id,b.section,b.parent_context,b.archived_at bullet_archived,v.id variant_id,v.body,v.updated_at,v.archived_at variant_archived FROM bullets b JOIN bullet_variants v ON v.bullet_id=b.id AND v.user_id=b.user_id WHERE b.id=%s AND v.id=%s AND b.user_id=%s"+clause,(bullet_id,variant_id,user_id))

async def _relationships(conn,cid):
    return await _many(conn,"""SELECT cb.id,cb.bullet_id,cb.variant_id,cb.destination_section,cb.destination_parent_type,cb.destination_parent_id,cb.sort_order,cb.wording_snapshot,cb.snapshot_source_updated_at,b.archived_at bullet_archived,v.archived_at variant_archived,v.body current_body,v.updated_at current_updated_at FROM composition_bullets cb LEFT JOIN bullets b ON b.id=cb.bullet_id LEFT JOIN bullet_variants v ON v.id=cb.variant_id WHERE cb.composition_id=%s ORDER BY cb.destination_section,cb.destination_parent_id,cb.sort_order,cb.id""",(cid,))

async def _snapshot(conn,row,resume=None):
    rels=await _relationships(conn,row["id"])
    return {"name":row["name"],"description":row.get("description","") ,"display_title":row.get("display_title","") ,"target_company":row.get("target_company","") ,"target_role":row.get("target_role","") ,"preferred_page_length":row.get("preferred_page_length",1),"date_format":row.get("date_format","long"),"section_sort_modes":row.get("section_sort_modes",{}),"resume":resume or row["render_payload"],"interest_layout":row.get("interest_layout","compact"),"section_order":row.get("section_order",[]),"bullet_placements":[{k:(str(v) if k.endswith("_id") and v is not None else v) for k,v in x.items() if k in {"id","bullet_id","variant_id","destination_section","destination_parent_type","destination_parent_id","sort_order","wording_snapshot","snapshot_source_updated_at"}} for x in rels]}

async def apply_placements(conn,user_id,cid,resume):
    rels=await _relationships(conn,cid)
    selected=await _many(conn,"SELECT section,item_id FROM composition_items WHERE composition_id=%s",(cid,))
    included={(x["section"],str(x["item_id"])) for x in selected}
    grouped={}
    for rel in rels: grouped.setdefault((rel["destination_section"],str(rel["destination_parent_id"])),[]).append(rel)
    for section,pid in included:
        key=section; rows=grouped.get((section,pid),[]); bodies=[x["wording_snapshot"] for x in rows]
        if section in {"projects","work_experience","leadership","education","tool_groups"}:
            for entry in resume.get(section,[]):
                if str(entry.get("id"))==pid: entry["bullets"]=bodies
        elif section=="personal_interests":
            for entry in resume.get("personal_interest_items",[]):
                if str(entry.get("id"))==pid: entry["bullets"]=bodies
        elif section=="custom_sections":
            for sec in resume.get("custom_sections",[]):
                for entry in sec.get("entries",[]):
                    if str(entry.get("id"))==pid: entry["bullets"]=bodies
    return resume
async def _commit(conn,user_id,locked,source):
    resume=await apply_placements(conn,user_id,locked["id"],locked["render_payload"])
    row=await _one(conn,"UPDATE resume_compositions SET render_payload=%s::jsonb,revision=revision+1,autosaved_at=now(),updated_at=now() WHERE id=%s AND user_id=%s RETURNING *",(json.dumps(resume),locked["id"],user_id))
    snap=await _snapshot(conn,row,resume)
    await conn.execute("INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,%s,%s::jsonb)",(row["id"],user_id,row["revision"],source,json.dumps(snap,default=str)))
    return row

async def picker(conn,user_id,q,section,limit,offset):
    like=f"%{q.strip()}%"
    return await _many(conn,"""SELECT b.id,b.section,b.parent_context,b.created_at,b.updated_at,count(v.id) FILTER(WHERE v.archived_at IS NULL) variant_count,jsonb_agg(jsonb_build_object('id',v.id,'name',v.name,'body',v.body,'is_default',v.is_default) ORDER BY v.is_default DESC,v.sort_order,v.id) FILTER(WHERE v.archived_at IS NULL) variants FROM bullets b JOIN bullet_variants v ON v.bullet_id=b.id AND v.user_id=b.user_id WHERE b.user_id=%s AND b.archived_at IS NULL AND v.archived_at IS NULL AND (%s='' OR b.section=%s) AND (v.body ILIKE %s OR COALESCE(b.parent_context,'') ILIKE %s) GROUP BY b.id ORDER BY min(lower(v.body)),b.id LIMIT %s OFFSET %s""",(user_id,section,section,like,like,limit,offset))

async def insert_placement(conn,user_id,cid,payload):
    async with conn.transaction():
        locked,error=await _lock_composition(conn,user_id,cid,payload.revision)
        if error:return None,error
        if not await _destination(conn,user_id,payload.destination_parent_type,payload.destination_parent_id):return None,"missing"
        if not await _one(conn,"SELECT 1 FROM composition_items WHERE composition_id=%s AND section=%s AND item_id=%s",(cid,payload.destination_section,payload.destination_parent_id)):return None,"missing"
        if await _one(conn,"SELECT 1 FROM composition_bullets WHERE composition_id=%s AND bullet_id=%s",(cid,payload.bullet_id)):return None,"duplicate"
        selected=await _bullet_variant(conn,user_id,payload.bullet_id,payload.variant_id,True)
        if not selected:return None,"missing"
        order=payload.sort_order
        if order is None:
            r=await _one(conn,"SELECT COALESCE(max(sort_order)+1,0) n FROM composition_bullets WHERE composition_id=%s AND destination_parent_type=%s AND destination_parent_id=%s",(cid,payload.destination_parent_type,payload.destination_parent_id));order=r["n"]
        await conn.execute("INSERT INTO composition_bullets(composition_id,bullet_id,variant_id,destination_section,destination_parent_type,destination_parent_id,sort_order,wording_snapshot,snapshot_source_updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",(cid,payload.bullet_id,payload.variant_id,payload.destination_section,payload.destination_parent_type,payload.destination_parent_id,order,selected["body"],selected["updated_at"]))
        return await _commit(conn,user_id,locked,"bullet-placement-insert"),None

async def create_and_place(conn,user_id,cid,payload):
    async with conn.transaction():
        locked,error=await _lock_composition(conn,user_id,cid,payload.revision)
        if error:return None,error
        if not await _destination(conn,user_id,payload.destination_parent_type,payload.destination_parent_id):return None,"missing"
        parent_col={"content_item":"parent_id","education_item":"education_item_id","tool_group":"tool_group_id","interest":"interest_id","custom_entry":"custom_entry_id"}[payload.destination_parent_type]
        label=(await _one(conn,"SELECT phase3c1_parent_label(%s,%s,%s) label",(user_id,payload.destination_parent_type,payload.destination_parent_id)))["label"]
        bullet=await _one(conn,f"INSERT INTO bullets(user_id,{parent_col},section,parent_context,sort_order) VALUES(%s,NULL,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM bullets WHERE user_id=%s AND section=%s)) RETURNING id",(user_id,payload.library_section,label,user_id,payload.library_section))
        variant=await _one(conn,"INSERT INTO bullet_variants(user_id,bullet_id,name,body,is_default,sort_order) VALUES(%s,%s,%s,%s,true,0) RETURNING id,body,updated_at",(user_id,bullet["id"],payload.variant_name.strip(),payload.body.strip()))
        order=(await _one(conn,"SELECT COALESCE(max(sort_order)+1,0) n FROM composition_bullets WHERE composition_id=%s AND destination_parent_type=%s AND destination_parent_id=%s",(cid,payload.destination_parent_type,payload.destination_parent_id)))["n"]
        await conn.execute("INSERT INTO composition_bullets(composition_id,bullet_id,variant_id,destination_section,destination_parent_type,destination_parent_id,sort_order,wording_snapshot,snapshot_source_updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",(cid,bullet["id"],variant["id"],payload.destination_section,payload.destination_parent_type,payload.destination_parent_id,order,variant["body"],variant["updated_at"]))
        return await _commit(conn,user_id,locked,"bullet-create-and-place"),None

async def remove_placement(conn,user_id,cid,placement_id,revision):
    async with conn.transaction():
        locked,error=await _lock_composition(conn,user_id,cid,revision)
        if error:return None,error
        row=await _one(conn,"DELETE FROM composition_bullets cb USING resume_compositions c WHERE cb.id=%s AND cb.composition_id=%s AND c.id=cb.composition_id AND c.user_id=%s RETURNING cb.destination_parent_type,cb.destination_parent_id",(placement_id,cid,user_id))
        if not row:return None,"missing"
        rows=await _many(conn,"SELECT id FROM composition_bullets WHERE composition_id=%s AND destination_parent_type=%s AND destination_parent_id=%s ORDER BY sort_order,id",(cid,row["destination_parent_type"],row["destination_parent_id"]))
        for i,x in enumerate(rows):await conn.execute("UPDATE composition_bullets SET sort_order=%s,updated_at=now() WHERE id=%s",(i,x["id"]))
        return await _commit(conn,user_id,locked,"bullet-placement-remove"),None

async def replace_placement(conn,user_id,cid,placement_id,payload):
    async with conn.transaction():
        locked,error=await _lock_composition(conn,user_id,cid,payload.revision)
        if error:return None,error
        selected=await _bullet_variant(conn,user_id,payload.bullet_id,payload.variant_id,True)
        if not selected:return None,"missing"
        row=await _one(conn,"UPDATE composition_bullets cb SET bullet_id=%s,variant_id=%s,wording_snapshot=%s,snapshot_source_updated_at=%s,updated_at=now() FROM resume_compositions c WHERE cb.id=%s AND cb.composition_id=%s AND c.id=cb.composition_id AND c.user_id=%s RETURNING cb.id",(payload.bullet_id,payload.variant_id,selected["body"],selected["updated_at"],placement_id,cid,user_id))
        if not row:return None,"missing"
        return await _commit(conn,user_id,locked,"bullet-placement-replace"),None

async def reorder_placements(conn,user_id,cid,payload):
    async with conn.transaction():
        locked,error=await _lock_composition(conn,user_id,cid,payload.revision)
        if error:return None,error
        rows=await _many(conn,"SELECT cb.id FROM composition_bullets cb JOIN resume_compositions c ON c.id=cb.composition_id WHERE cb.composition_id=%s AND c.user_id=%s AND cb.destination_section=%s AND cb.destination_parent_type=%s AND cb.destination_parent_id=%s ORDER BY cb.sort_order,cb.id FOR UPDATE",(cid,user_id,payload.destination_section,payload.destination_parent_type,payload.destination_parent_id))
        if {str(x["id"]) for x in rows}!={str(x) for x in payload.ids}:return None,"invalid"
        for i,rid in enumerate(payload.ids):await conn.execute("UPDATE composition_bullets SET sort_order=%s,updated_at=now() WHERE id=%s AND composition_id=%s",(i,rid,cid))
        return await _commit(conn,user_id,locked,"bullet-placement-reorder"),None

async def update_usage(conn,user_id,cid,placement_id,revision):
    async with conn.transaction():
        locked,error=await _lock_composition(conn,user_id,cid,revision)
        if error:return None,error
        row=await _one(conn,"UPDATE composition_bullets cb SET wording_snapshot=v.body,snapshot_source_updated_at=v.updated_at,updated_at=now() FROM bullet_variants v,resume_compositions c WHERE cb.id=%s AND cb.composition_id=%s AND c.id=cb.composition_id AND c.user_id=%s AND v.id=cb.variant_id RETURNING cb.id",(placement_id,cid,user_id))
        if not row:return None,"missing"
        return await _commit(conn,user_id,locked,"bullet-usage-update"),None

async def usage_rows(conn,user_id,cid):
    rows=await _many(conn,"""SELECT cb.*,v.name variant_name,(SELECT count(*) FROM bullet_variants av WHERE av.bullet_id=cb.bullet_id AND av.archived_at IS NULL) active_variant_count,CASE WHEN b.id IS NULL OR v.id IS NULL THEN 'missing' WHEN b.archived_at IS NOT NULL OR v.archived_at IS NOT NULL THEN 'archived' WHEN cb.wording_snapshot IS DISTINCT FROM v.body OR cb.snapshot_source_updated_at IS DISTINCT FROM v.updated_at THEN 'outdated' ELSE 'current' END usage_status FROM composition_bullets cb JOIN resume_compositions c ON c.id=cb.composition_id LEFT JOIN bullets b ON b.id=cb.bullet_id LEFT JOIN bullet_variants v ON v.id=cb.variant_id WHERE cb.composition_id=%s AND c.user_id=%s ORDER BY cb.destination_section,cb.destination_parent_id,cb.sort_order,cb.id""",(cid,user_id))
    return rows


