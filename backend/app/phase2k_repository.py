from psycopg.rows import dict_row
async def many(c,q,p=()):
 async with c.cursor(row_factory=dict_row) as x: await x.execute(q,p);return await x.fetchall()
async def one(c,q,p=()):
 x=await many(c,q,p);return x[0] if x else None
def norm(s):
 d=s.strip()
 if not d: raise ValueError("Tag name cannot be blank")
 return d,d.casefold()
async def counts(c,u):
 x=await many(c,"SELECT section,count(*) count FROM bullets WHERE user_id=%s AND archived_at IS NULL GROUP BY section",(u,));z={a['section']:a['count'] for a in x};z['all']=sum(z.values());return z
async def tags(c,u,q=""):
 return await many(c,"SELECT id,display_name,normalized_name,created_at,updated_at FROM library_tags WHERE user_id=%s AND normalized_name LIKE %s ORDER BY normalized_name,id",(u,f"%{q.strip().casefold()}%"))
async def upsert_tag(c,u,n):
 d,k=norm(n);return await one(c,"INSERT INTO library_tags(user_id,display_name,normalized_name) VALUES(%s,%s,%s) ON CONFLICT(user_id,normalized_name) DO UPDATE SET updated_at=library_tags.updated_at RETURNING *",(u,d,k))
async def items(c,u,q,status,section,tag_ids,page,size):
 w=["b.user_id=%s"];p=[u]
 if status=="active":w+=["b.archived_at IS NULL"]
 if status=="archived":w+=["b.archived_at IS NOT NULL"]
 if section:w+=["b.section=%s"];p+=[section]
 if q.strip():
  like=f"%{q.strip()}%";w+=["(d.body ILIKE %s OR b.parent_context ILIKE %s OR EXISTS(SELECT 1 FROM library_bullet_tags bt JOIN library_tags t ON t.id=bt.tag_id WHERE bt.bullet_id=b.id AND t.display_name ILIKE %s))"];p += [like,like,like]
 if tag_ids:w+=["b.id IN(SELECT bullet_id FROM library_bullet_tags WHERE tag_id=ANY(%s) GROUP BY bullet_id HAVING count(DISTINCT tag_id)=%s)"];p += [tag_ids,len(tag_ids)]
 pred=" AND ".join(w);total=(await one(c,f"SELECT count(*) total FROM bullets b LEFT JOIN LATERAL(SELECT body FROM bullet_variants v WHERE v.bullet_id=b.id ORDER BY v.is_default DESC,v.sort_order,v.id LIMIT 1)d ON true WHERE {pred}",p))["total"]
 rows=await many(c,f"""SELECT b.id,b.section,b.parent_id,b.parent_context,b.archived_at,b.created_at,b.updated_at,COALESCE(d.body,'') body,(SELECT count(*) FROM bullet_variants v WHERE v.bullet_id=b.id) variant_count,COALESCE((SELECT json_agg(json_build_object('id',t.id,'display_name',t.display_name) ORDER BY t.normalized_name,t.id) FROM library_bullet_tags bt JOIN library_tags t ON t.id=bt.tag_id WHERE bt.bullet_id=b.id),'[]'::json) tags FROM bullets b LEFT JOIN LATERAL(SELECT body FROM bullet_variants v WHERE v.bullet_id=b.id AND v.archived_at IS NULL ORDER BY v.is_default DESC,v.sort_order,v.id LIMIT 1)d ON true WHERE {pred} ORDER BY lower(COALESCE(d.body,'')),b.updated_at DESC,b.id LIMIT %s OFFSET %s""",p+[size,(page-1)*size])
 pages=(total+size-1)//size;return dict(items=rows,page=page,page_size=size,total_items=total,total_pages=pages,has_previous=page>1,has_next=page<pages)
async def create_item(c,u,x):
 async with c.transaction():
  b=await one(c,"INSERT INTO bullets(user_id,parent_id,section,parent_context,sort_order) VALUES(%s,NULL,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM bullets WHERE user_id=%s AND section=%s)) RETURNING id",(u,x.section,x.parent_context.strip() or None,u,x.section));v=await one(c,"INSERT INTO bullet_variants(user_id,bullet_id,name,body,is_default,sort_order) VALUES(%s,%s,%s,%s,true,0) RETURNING id",(u,b['id'],x.variant_name.strip(),x.body.strip()))
  for n in x.tags:
   t=await upsert_tag(c,u,n);await c.execute("INSERT INTO library_bullet_tags VALUES(%s,%s,now()) ON CONFLICT DO NOTHING",(b['id'],t['id']))
  return {'id':b['id'],'variant_id':v['id']}
async def replace_tags(c,u,bid,names):
 async with c.transaction():
  if not await one(c,"SELECT id FROM bullets WHERE id=%s AND user_id=%s FOR UPDATE",(bid,u)):return None
  await c.execute("DELETE FROM library_bullet_tags WHERE bullet_id=%s",(bid,))
  for n in names:
   t=await upsert_tag(c,u,n);await c.execute("INSERT INTO library_bullet_tags(bullet_id,tag_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",(bid,t['id']))
  return {'id':bid}
async def bulk(c,u,ids,action,names,section):
 async with c.transaction():
  own=await many(c,"SELECT id FROM bullets WHERE user_id=%s AND id=ANY(%s) FOR UPDATE",(u,ids))
  if {x['id'] for x in own}!=set(ids):return None
  if action in ('archive','restore'):await c.execute(f"UPDATE bullets SET archived_at={'now()' if action=='archive' else 'NULL'},updated_at=now() WHERE user_id=%s AND id=ANY(%s)",(u,ids))
  elif action=='move-section':await c.execute("UPDATE bullets SET section=%s,updated_at=now() WHERE user_id=%s AND id=ANY(%s)",(section,u,ids))
  else:
   tids=[(await upsert_tag(c,u,n))['id'] for n in names]
   if action=='add-tags':
    for bid in ids:
     for tid in tids:await c.execute("INSERT INTO library_bullet_tags(bullet_id,tag_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",(bid,tid))
   else:await c.execute("DELETE FROM library_bullet_tags WHERE bullet_id=ANY(%s) AND tag_id=ANY(%s)",(ids,tids))
  return {'succeeded':ids,'failed':[]}
async def usages(c,u,bid):
 return await many(c,"""SELECT cb.id placement_id,c.id composition_id,c.name resume_name,cb.destination_section section,cb.destination_parent_type,cb.destination_parent_id,cb.variant_id,v.name variant_name,CASE WHEN b.archived_at IS NOT NULL OR v.archived_at IS NOT NULL THEN 'Archived' WHEN cb.wording_snapshot IS NULL THEN 'Missing' WHEN cb.snapshot_source_updated_at=v.updated_at THEN 'Current' ELSE 'Outdated' END status FROM composition_bullets cb JOIN resume_compositions c ON c.id=cb.composition_id JOIN bullets b ON b.id=cb.bullet_id LEFT JOIN bullet_variants v ON v.id=cb.variant_id WHERE cb.bullet_id=%s AND c.user_id=%s ORDER BY lower(c.name),c.id,cb.id""",(bid,u))


async def detail(c,u,bid):
 item=await one(c,"""SELECT b.id,b.section,b.parent_context,b.archived_at,b.created_at,b.updated_at,COALESCE(d.body,'') body FROM bullets b LEFT JOIN LATERAL(SELECT body FROM bullet_variants v WHERE v.bullet_id=b.id ORDER BY v.is_default DESC,v.sort_order,v.id LIMIT 1)d ON true WHERE b.id=%s AND b.user_id=%s""",(bid,u))
 if not item:return None
 item['variants']=await many(c,"SELECT id,name,body,is_default,sort_order,archived_at,created_at,updated_at FROM bullet_variants WHERE bullet_id=%s AND user_id=%s ORDER BY sort_order,id",(bid,u))
 item['tags']=await many(c,"SELECT t.id,t.display_name,t.normalized_name FROM library_bullet_tags bt JOIN library_tags t ON t.id=bt.tag_id WHERE bt.bullet_id=%s AND t.user_id=%s ORDER BY t.normalized_name,t.id",(bid,u))
 item['usage']=await usages(c,u,bid)
 item['parent_id']=item.get('parent_id')
 item['parent_type']='content_item' if item.get('parent_id') else None
 item['parent_options']=await parent_options(c,u)
 return item

async def parent_options(c,u):
 return await many(c,"""SELECT id,'content_item' type,CASE kind WHEN 'employment' THEN 'experience' ELSE kind END section,CASE WHEN kind='project' THEN COALESCE(name,'') ELSE concat_ws(' — ',organization,title) END label FROM content_items WHERE user_id=%s AND archived_at IS NULL AND kind IN ('employment','project','leadership') ORDER BY kind,lower(CASE WHEN kind='project' THEN COALESCE(name,'') ELSE concat_ws(' — ',organization,title) END),id""",(u,))
async def update_parent(c,u,bid,parent_id,parent_type):
 async with c.transaction():
  bullet=await one(c,"SELECT id,section,parent_id FROM bullets WHERE id=%s AND user_id=%s FOR UPDATE",(bid,u))
  if not bullet:return None,'missing'
  if parent_id is None:
   row=await one(c,"UPDATE bullets SET parent_id=NULL,parent_context=NULL,updated_at=now() WHERE id=%s AND user_id=%s RETURNING id,parent_id,parent_context",(bid,u));return row,None
  if parent_type!='content_item':return None,'invalid'
  expected={'experience':'employment','projects':'project','leadership':'leadership'}.get(bullet['section'])
  parent=await one(c,"SELECT id,kind,CASE WHEN kind='project' THEN COALESCE(name,'') ELSE concat_ws(' — ',organization,title) END label FROM content_items WHERE id=%s AND user_id=%s AND archived_at IS NULL",(parent_id,u))
  if not parent:return None,'missing'
  if not expected or parent['kind']!=expected:return None,'invalid'
  row=await one(c,"UPDATE bullets SET parent_id=%s,parent_context=%s,updated_at=now() WHERE id=%s AND user_id=%s RETURNING id,parent_id,parent_context",(parent_id,parent['label'],bid,u));return row,None
