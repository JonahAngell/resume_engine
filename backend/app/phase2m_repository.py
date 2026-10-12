

from copy import deepcopy
from psycopg.rows import dict_row
from .phase2l import preprocess_resume
from .render import normalize_skill_row_max, normalize_template_style

RENDERER_CONTRACT_VERSION = "2m.1"

async def one(conn, sql, params=()):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        return await cur.fetchone()

async def materialize_composition(conn, user_id, composition_id, revision=None):
    params=[composition_id,user_id]
    revision_clause=""
    if revision is not None:
        revision_clause=" AND revision=%s"; params.append(revision)
    row=await one(conn, """SELECT id,name,revision,render_payload,preferred_page_length,date_format,template_style,skill_row_max,section_sort_modes,section_order,interest_layout,archived_at FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL"""+revision_clause, tuple(params))
    if not row:
        exists=await one(conn,"SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",(composition_id,user_id))
        return None, "stale" if exists and revision is not None else "missing"
    resume=deepcopy(row["render_payload"])
    resume["section_order"]=row.get("section_order") or resume.get("section_order",[])
    resume["interest_layout"]=row.get("interest_layout") or resume.get("interest_layout","compact")
    resume=preprocess_resume(resume,row.get("section_sort_modes") or {},row.get("date_format") or "long")
    # Hidden state is authoritative in section_order and never mutates Library data.
    resume["section_order"]=[x for x in resume.get("section_order",[]) if not str(x).startswith("hidden:")]
    return {"composition_id":str(row["id"]),"revision":row["revision"],"name":row["name"],"preferred_page_count":row["preferred_page_length"],"renderer_contract_version":RENDERER_CONTRACT_VERSION,"section_sort_modes":row.get("section_sort_modes") or {},"date_format":row.get("date_format") or "long","template_style":normalize_template_style(row.get("template_style")),"skill_row_max":normalize_skill_row_max(row.get("skill_row_max")),"resume":resume},None


async def materialize_revision(conn,user_id,composition_id,revision_id):
    row=await one(conn,"""SELECT r.snapshot,c.preferred_page_length,c.date_format,c.template_style,c.skill_row_max,c.section_sort_modes FROM composition_revisions r JOIN resume_compositions c ON c.id=r.composition_id WHERE r.id=%s AND r.composition_id=%s AND r.user_id=%s AND c.user_id=%s""",(revision_id,composition_id,user_id,user_id))
    if not row:return None,"missing"
    snapshot=row["snapshot"] or {}; resume=deepcopy(snapshot.get("resume") or {})
    resume["section_order"]=snapshot.get("section_order",resume.get("section_order",[]));resume["interest_layout"]=snapshot.get("interest_layout",resume.get("interest_layout","compact"))
    modes=snapshot.get("section_sort_modes",row["section_sort_modes"] or {});date_format=snapshot.get("date_format",row["date_format"] or "long")
    template_style=normalize_template_style(snapshot.get("template_style"), row.get("template_style") or "classic")
    skill_row_max=normalize_skill_row_max(snapshot.get("skill_row_max"), row.get("skill_row_max") or 4)
    resume=preprocess_resume(resume,modes,date_format);resume["section_order"]=[x for x in resume.get("section_order",[]) if not str(x).startswith("hidden:")]
    return {"resume":resume,"section_sort_modes":modes,"date_format":date_format,"template_style":template_style,"skill_row_max":skill_row_max,"renderer_contract_version":RENDERER_CONTRACT_VERSION},None
