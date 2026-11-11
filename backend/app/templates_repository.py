"""Custom resume templates: storage, linking resumes, and what a resume renders with."""

import json

from psycopg.rows import dict_row

from .render import normalize_template_style
from .template_settings import resolve_settings

_COLUMNS = "t.id,t.name,t.base_style,t.settings,t.revision,t.created_at,t.updated_at"


async def _one(conn, sql, params=()):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        return await cur.fetchone()


async def _many(conn, sql, params=()):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        return await cur.fetchall()


def public(row: dict) -> dict:
    """A template as the API returns it, with complete settings."""
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "base_style": row["base_style"],
        "settings": resolve_settings(row["base_style"], row.get("settings")),
        "revision": row["revision"],
        "used_by": int(row.get("used_by") or 0),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


async def list_templates(conn, user_id) -> list[dict]:
    rows = await _many(
        conn,
        f"""SELECT {_COLUMNS},
                   (SELECT count(*) FROM resume_compositions c
                     WHERE c.template_id=t.id AND c.archived_at IS NULL) AS used_by
              FROM resume_templates t WHERE t.user_id=%s ORDER BY lower(t.name),t.id""",
        (user_id,),
    )
    return [public(row) for row in rows]


async def get_template(conn, user_id, template_id) -> dict | None:
    row = await _one(
        conn,
        f"""SELECT {_COLUMNS},
                   (SELECT count(*) FROM resume_compositions c
                     WHERE c.template_id=t.id AND c.archived_at IS NULL) AS used_by
              FROM resume_templates t WHERE t.id=%s AND t.user_id=%s""",
        (template_id, user_id),
    )
    return public(row) if row else None


async def _name_taken(conn, user_id, name, exclude=None) -> bool:
    row = await _one(
        conn,
        "SELECT id FROM resume_templates WHERE user_id=%s AND lower(name)=lower(%s) AND (%s::uuid IS NULL OR id<>%s::uuid)",
        (user_id, name.strip(), exclude, exclude),
    )
    return bool(row)


async def create_template(conn, user_id, name: str, base_style: str, settings: dict | None):
    base = normalize_template_style(base_style)
    resolved = resolve_settings(base, settings)
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"templates:{user_id}",))
        if await _name_taken(conn, user_id, name):
            return None, "name"
        row = await _one(
            conn,
            "INSERT INTO resume_templates(user_id,name,base_style,settings) VALUES(%s,%s,%s,%s::jsonb) RETURNING id",
            (user_id, name.strip(), base, json.dumps(resolved)),
        )
    return await get_template(conn, user_id, row["id"]), None


async def _record_linked(conn, user_id, template_id, source: str, note: str, unlink: bool = False) -> None:
    """Bump each linked resume's revision and record it in that resume's history.

    The snapshot trigger adds the template's settings at this moment, so history keeps the look.
    """
    rows = await _many(
        conn,
        f"""UPDATE resume_compositions SET {'template_id=NULL,' if unlink else ''}revision=revision+1,updated_at=now()
             WHERE template_id=%s AND user_id=%s AND archived_at IS NULL
         RETURNING id,revision,render_payload,preferred_page_length,date_format,template_style,skill_row_max,section_sort_modes""",
        (template_id, user_id),
    )
    for row in rows:
        await conn.execute(
            "INSERT INTO composition_revisions(composition_id,user_id,revision,source,note,snapshot) VALUES(%s,%s,%s,%s,%s,%s::jsonb)",
            (
                row["id"],
                user_id,
                row["revision"],
                source,
                note,
                json.dumps(
                    {
                        "resume": row["render_payload"],
                        "preferred_page_length": row["preferred_page_length"],
                        "date_format": row["date_format"],
                        "template_style": row["template_style"],
                        "skill_row_max": row["skill_row_max"],
                        "section_sort_modes": row["section_sort_modes"],
                    }
                ),
            ),
        )


async def update_template(conn, user_id, template_id, revision: int, name: str, settings: dict | None):
    async with conn.transaction():
        current = await _one(
            conn, "SELECT id,base_style,revision FROM resume_templates WHERE id=%s AND user_id=%s FOR UPDATE", (template_id, user_id)
        )
        if not current:
            return None, "missing"
        if current["revision"] != revision:
            return None, "stale"
        if await _name_taken(conn, user_id, name, str(template_id)):
            return None, "name"
        resolved = resolve_settings(current["base_style"], settings)
        await conn.execute(
            "UPDATE resume_templates SET name=%s,settings=%s::jsonb,revision=revision+1,updated_at=now() WHERE id=%s AND user_id=%s",
            (name.strip(), json.dumps(resolved), template_id, user_id),
        )
        await _record_linked(conn, user_id, template_id, "template-update", f"Template “{name.strip()}” changed")
    return await get_template(conn, user_id, template_id), None


async def delete_template(conn, user_id, template_id):
    """Linked resumes go back to the template's built-in style, with a history entry."""
    async with conn.transaction():
        row = await _one(conn, "SELECT id,name FROM resume_templates WHERE id=%s AND user_id=%s FOR UPDATE", (template_id, user_id))
        if not row:
            return "missing"
        await _record_linked(conn, user_id, template_id, "template-deleted", f"Template “{row['name']}” deleted", unlink=True)
        await conn.execute("DELETE FROM resume_templates WHERE id=%s AND user_id=%s", (template_id, user_id))
    return None


async def owned_template(conn, user_id, template_id) -> dict | None:
    return await _one(conn, "SELECT id,base_style FROM resume_templates WHERE id=%s AND user_id=%s", (template_id, user_id))


async def appearance_for(conn, user_id, template_id, tools_layout) -> dict:
    """What a resume renders with: its custom template's settings (None for a built-in) and its
    own Tools layout choice (None follows the template)."""
    settings = None
    name = None
    if template_id:
        row = await _one(conn, "SELECT name,base_style,settings FROM resume_templates WHERE id=%s AND user_id=%s", (template_id, user_id))
        if row:
            settings = resolve_settings(row["base_style"], row["settings"])
            name = row["name"]
    return {"settings": settings, "tools_layout": tools_layout, "template_id": str(template_id) if settings else None, "template_name": name}


def appearance_from_snapshot(snapshot: dict, template_style: str) -> dict:
    """The look a revision recorded. Older revisions carry no template fields and are built-in."""
    stored = snapshot.get("template_settings")
    settings = resolve_settings(template_style, stored) if isinstance(stored, dict) else None
    return {
        "settings": settings,
        "tools_layout": snapshot.get("tools_layout"),
        "template_id": snapshot.get("template_id") if settings else None,
        "template_name": snapshot.get("template_name") if settings else None,
    }
