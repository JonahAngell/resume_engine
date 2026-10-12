
import json
from psycopg.rows import dict_row
async def one(c,q,p=()):
 async with c.cursor(row_factory=dict_row) as x:await x.execute(q,p);return await x.fetchone()
async def update_preferences(c,u,cid,req):
 async with c.transaction():
  row=await one(c,"UPDATE resume_compositions SET preferred_page_length=%s,date_format=%s,template_style=%s,skill_row_max=%s,section_sort_modes=%s::jsonb,revision=revision+1,updated_at=now() WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s RETURNING *",(req.preferred_page_length,req.date_format,req.template_style,req.skill_row_max,json.dumps(req.section_sort_modes),cid,u,req.revision))
  if not row:
    exists=await one(c,"SELECT id FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",(cid,u));return None,"stale" if exists else "missing"
  await c.execute("INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,'phase2l-preferences',%s::jsonb)",(cid,u,row['revision'],json.dumps({'resume':row['render_payload'],'preferred_page_length':row['preferred_page_length'],'date_format':row['date_format'],'template_style':row['template_style'],'skill_row_max':row['skill_row_max'],'section_sort_modes':row['section_sort_modes']})))
  return row,None

