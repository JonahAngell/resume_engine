import json
from psycopg.rows import dict_row
from .templates_repository import owned_template
async def one(c,q,p=()):
 async with c.cursor(row_factory=dict_row) as x:await x.execute(q,p);return await x.fetchone()
async def update_preferences(c,u,cid,req):
 async with c.transaction():
  current=await one(c,"SELECT template_id,tools_layout FROM resume_compositions WHERE id=%s AND user_id=%s AND archived_at IS NULL",(cid,u))
  if not current:return None,"missing"
  # template_id and tools_layout change only when the request names them.
  sent=req.model_fields_set
  template_id=req.template_id if "template_id" in sent else current["template_id"]
  tools_layout=req.tools_layout if "tools_layout" in sent else current["tools_layout"]
  style=req.template_style
  if template_id is not None:
   template=await owned_template(c,u,template_id)
   if not template:return None,"template"
   # A custom template renders on its built-in style.
   style=template["base_style"]
  row=await one(c,"UPDATE resume_compositions SET preferred_page_length=%s,date_format=%s,template_style=%s,skill_row_max=%s,template_id=%s,tools_layout=%s,section_sort_modes=%s::jsonb,revision=revision+1,updated_at=now() WHERE id=%s AND user_id=%s AND archived_at IS NULL AND revision=%s RETURNING *",(req.preferred_page_length,req.date_format,style,req.skill_row_max,template_id,tools_layout,json.dumps(req.section_sort_modes),cid,u,req.revision))
  if not row:return None,"stale"
  await c.execute("INSERT INTO composition_revisions(composition_id,user_id,revision,source,snapshot) VALUES(%s,%s,%s,'phase2l-preferences',%s::jsonb)",(cid,u,row['revision'],json.dumps({'resume':row['render_payload'],'preferred_page_length':row['preferred_page_length'],'date_format':row['date_format'],'template_style':row['template_style'],'skill_row_max':row['skill_row_max'],'section_sort_modes':row['section_sort_modes']})))
  return row,None
