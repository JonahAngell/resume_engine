"""Defaults sets: named groups of library records a new resume can start from."""

from psycopg import errors

from .editing_repository import many, one
from .resume_variants import Selection

ITEM_TYPES = (
    "content_item",
    "education_item",
    "tool_group",
    "interest",
    "custom_section",
    "summary",
    "profile",
    "bullet",
)
_SECTION_TYPES = {
    "projects": "content_item",
    "work_experience": "content_item",
    "leadership": "content_item",
    "education": "education_item",
    "tool_groups": "tool_group",
    "personal_interests": "interest",
}
_SET_ROW = """s.id,s.name,s.description,s.is_default,s.sort_order,s.archived_at,s.created_at,s.updated_at,
              (SELECT count(*) FROM default_set_members m WHERE m.set_id=s.id AND m.item_type<>'bullet') entry_count,
              (SELECT count(*) FROM default_set_members m WHERE m.set_id=s.id AND m.item_type='bullet') bullet_count"""


async def list_sets(conn, user_id, include_archived=False):
    return await many(
        conn,
        f"""SELECT {_SET_ROW} FROM default_sets s
            WHERE s.user_id=%s {"" if include_archived else "AND s.archived_at IS NULL"}
            ORDER BY s.archived_at IS NOT NULL, s.sort_order, lower(s.name), s.id""",
        (user_id,),
    )


async def get_set(conn, user_id, set_id):
    return await one(
        conn,
        f"SELECT {_SET_ROW} FROM default_sets s WHERE s.id=%s AND s.user_id=%s",
        (set_id, user_id),
    )


async def list_members(conn, user_id):
    """Every membership of the user's active sets, for the library UI."""
    return await many(
        conn,
        """SELECT m.set_id,m.item_type,m.item_id,m.variant_id
           FROM default_set_members m JOIN default_sets s ON s.id=m.set_id
           WHERE s.user_id=%s AND s.archived_at IS NULL
           ORDER BY m.set_id,m.item_type,m.sort_order,m.item_id""",
        (user_id,),
    )


async def _name_taken(conn, user_id, name, set_id=None):
    return await one(
        conn,
        """SELECT id FROM default_sets
           WHERE user_id=%s AND lower(name)=lower(%s) AND archived_at IS NULL
             AND id IS DISTINCT FROM %s""",
        (user_id, name.strip(), set_id),
    )


async def create_set(conn, user_id, name, description=""):
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"sets:{user_id}",))
        if await _name_taken(conn, user_id, name):
            return None, "name"
        has_default = await one(
            conn,
            "SELECT id FROM default_sets WHERE user_id=%s AND is_default AND archived_at IS NULL",
            (user_id,),
        )
        row = await one(
            conn,
            """INSERT INTO default_sets(user_id,name,description,is_default,sort_order)
               VALUES(%s,%s,%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM default_sets WHERE user_id=%s))
               RETURNING id""",
            (user_id, name.strip(), description.strip(), not has_default, user_id),
        )
        return await get_set(conn, user_id, row["id"]), None


async def update_set(conn, user_id, set_id, name, description=""):
    async with conn.transaction():
        if await _name_taken(conn, user_id, name, set_id):
            return None, "name"
        row = await one(
            conn,
            """UPDATE default_sets SET name=%s,description=%s,updated_at=now()
               WHERE id=%s AND user_id=%s AND archived_at IS NULL RETURNING id""",
            (name.strip(), description.strip(), set_id, user_id),
        )
        return (await get_set(conn, user_id, row["id"]) if row else None), None


async def set_default(conn, user_id, set_id):
    async with conn.transaction():
        row = await one(
            conn,
            "SELECT id FROM default_sets WHERE id=%s AND user_id=%s AND archived_at IS NULL FOR UPDATE",
            (set_id, user_id),
        )
        if not row:
            return None
        await conn.execute(
            "UPDATE default_sets SET is_default=false,updated_at=now() WHERE user_id=%s AND is_default",
            (user_id,),
        )
        await conn.execute(
            "UPDATE default_sets SET is_default=true,updated_at=now() WHERE id=%s", (set_id,)
        )
        return await get_set(conn, user_id, set_id)


async def archive_set(conn, user_id, set_id, archived=True):
    async with conn.transaction():
        if not archived:
            current = await one(
                conn, "SELECT name FROM default_sets WHERE id=%s AND user_id=%s", (set_id, user_id)
            )
            if current and await _name_taken(conn, user_id, current["name"], set_id):
                return None, "name"
        row = await one(
            conn,
            f"""UPDATE default_sets SET archived_at={"now()" if archived else "NULL"},
                  is_default=CASE WHEN %s THEN false ELSE is_default END,updated_at=now()
               WHERE id=%s AND user_id=%s RETURNING id""",
            (archived, set_id, user_id),
        )
        if not row:
            return None, None
        # Keep one default whenever any active set remains.
        await conn.execute(
            """UPDATE default_sets SET is_default=true,updated_at=now()
               WHERE id=(SELECT id FROM default_sets WHERE user_id=%s AND archived_at IS NULL
                         ORDER BY sort_order,id LIMIT 1)
                 AND NOT EXISTS (SELECT 1 FROM default_sets
                                 WHERE user_id=%s AND is_default AND archived_at IS NULL)""",
            (user_id, user_id),
        )
        return await get_set(conn, user_id, set_id), None


async def set_memberships(conn, user_id, item_type, item_id, memberships):
    """Replace which sets one record belongs to; ``memberships`` is [(set_id, variant_id)]."""
    async with conn.transaction():
        await conn.execute(
            """DELETE FROM default_set_members m USING default_sets s
               WHERE s.id=m.set_id AND s.user_id=%s AND s.archived_at IS NULL
                 AND m.item_type=%s AND m.item_id=%s""",
            (user_id, item_type, item_id),
        )
        if item_type == "summary":
            # A set holds one summary; choosing this one replaces any other.
            await conn.execute(
                """DELETE FROM default_set_members WHERE item_type='summary'
                   AND set_id = ANY(%s::uuid[])""",
                ([set_id for set_id, _ in memberships],),
            )
        if item_type == "profile":
            await conn.execute(
                """DELETE FROM default_set_members WHERE item_type='profile'
                   AND set_id = ANY(%s::uuid[])""",
                ([set_id for set_id, _ in memberships],),
            )
        for set_id, variant_id in memberships:
            owned = await one(
                conn,
                "SELECT id FROM default_sets WHERE id=%s AND user_id=%s AND archived_at IS NULL",
                (set_id, user_id),
            )
            if not owned:
                return None
            try:
                await conn.execute(
                    """INSERT INTO default_set_members(set_id,item_type,item_id,variant_id,sort_order)
                       VALUES(%s,%s,%s,%s,
                              (SELECT COALESCE(max(sort_order)+1,0) FROM default_set_members
                               WHERE set_id=%s AND item_type=%s))""",
                    (set_id, item_type, item_id, variant_id, set_id, item_type),
                )
            except (errors.ForeignKeyViolation, errors.CheckViolation):
                raise ValueError("That record or wording is not in your library")
        return await many(
            conn,
            """SELECT m.set_id,m.item_type,m.item_id,m.variant_id
               FROM default_set_members m JOIN default_sets s ON s.id=m.set_id
               WHERE s.user_id=%s AND m.item_type=%s AND m.item_id=%s""",
            (user_id, item_type, item_id),
        )


async def bulk_bullets(conn, user_id, set_id, action, bullet_ids):
    async with conn.transaction():
        if not await one(
            conn,
            "SELECT id FROM default_sets WHERE id=%s AND user_id=%s AND archived_at IS NULL",
            (set_id, user_id),
        ):
            return None
        if action == "remove":
            await conn.execute(
                """DELETE FROM default_set_members
                   WHERE set_id=%s AND item_type='bullet' AND item_id = ANY(%s::uuid[])""",
                (set_id, bullet_ids),
            )
        else:
            await conn.execute(
                """INSERT INTO default_set_members(set_id,item_type,item_id,sort_order)
                   SELECT %s,'bullet',b.id,
                          (SELECT COALESCE(max(sort_order)+1,0) FROM default_set_members
                           WHERE set_id=%s AND item_type='bullet') + row_number() OVER (ORDER BY b.sort_order,b.id) - 1
                   FROM bullets b WHERE b.user_id=%s AND b.id = ANY(%s::uuid[])
                   ON CONFLICT DO NOTHING""",
                (set_id, set_id, user_id, bullet_ids),
            )
        return await get_set(conn, user_id, set_id)


async def load_selection(conn, user_id, set_id):
    """The set's contents as a resume Selection, or None when the set is missing."""
    found = await one(
        conn,
        "SELECT id FROM default_sets WHERE id=%s AND user_id=%s AND archived_at IS NULL",
        (set_id, user_id),
    )
    if not found:
        return None
    rows = await many(
        conn,
        """SELECT item_type,item_id,variant_id FROM default_set_members
           WHERE set_id=%s ORDER BY item_type,sort_order,item_id""",
        (set_id,),
    )
    selection = Selection()
    for row in rows:
        kind = row["item_type"]
        if kind == "bullet":
            selection.bullets[row["item_id"]] = row["variant_id"]
        elif kind == "summary":
            selection.summary_id = row["item_id"]
        elif kind == "profile":
            selection.profile_id = row["item_id"]
            selection.profile_variant_id = row["variant_id"]
        else:
            selection.items.setdefault(kind, {})[row["item_id"]] = row["variant_id"]
    return selection


async def default_set(conn, user_id):
    return await one(
        conn,
        "SELECT id FROM default_sets WHERE user_id=%s AND is_default AND archived_at IS NULL",
        (user_id,),
    )


async def save_from_composition(conn, user_id, cid, name, replace_id=None):
    """Make a defaults set (or refill one) from what a resume currently includes."""
    async with conn.transaction():
        source = await one(
            conn,
            """SELECT id,summary_variant_id,profile_id,profile_variant_id FROM resume_compositions
               WHERE id=%s AND user_id=%s AND archived_at IS NULL""",
            (cid, user_id),
        )
        if not source:
            return None, "missing"
        if replace_id:
            target = await one(
                conn,
                "SELECT id FROM default_sets WHERE id=%s AND user_id=%s AND archived_at IS NULL FOR UPDATE",
                (replace_id, user_id),
            )
            if not target:
                return None, "missing"
            set_id = target["id"]
            await conn.execute("DELETE FROM default_set_members WHERE set_id=%s", (set_id,))
        else:
            created, error = await create_set(conn, user_id, name)
            if error:
                return None, error
            set_id = created["id"]
        items = await many(
            conn,
            "SELECT section,item_id,variant_id,sort_order FROM composition_items WHERE composition_id=%s",
            (cid,),
        )
        for item in items:
            kind = _SECTION_TYPES.get(item["section"])
            if not kind:
                continue
            await conn.execute(
                """INSERT INTO default_set_members(set_id,item_type,item_id,variant_id,sort_order)
                   VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (
                    set_id,
                    kind,
                    item["item_id"],
                    item["variant_id"] if kind in ("content_item", "education_item") else None,
                    item["sort_order"],
                ),
            )
        await conn.execute(
            """INSERT INTO default_set_members(set_id,item_type,item_id,sort_order)
               SELECT %s,'custom_section',section_id,sort_order FROM composition_custom_sections
               WHERE composition_id=%s ON CONFLICT DO NOTHING""",
            (set_id, cid),
        )
        await conn.execute(
            """INSERT INTO default_set_members(set_id,item_type,item_id,variant_id,sort_order)
               SELECT %s,'bullet',bullet_id,variant_id,sort_order FROM composition_bullets
               WHERE composition_id=%s ON CONFLICT DO NOTHING""",
            (set_id, cid),
        )
        if source["summary_variant_id"]:
            await conn.execute(
                """INSERT INTO default_set_members(set_id,item_type,item_id) VALUES(%s,'summary',%s)
                   ON CONFLICT DO NOTHING""",
                (set_id, source["summary_variant_id"]),
            )
        if source["profile_id"]:
            await conn.execute(
                """INSERT INTO default_set_members(set_id,item_type,item_id,variant_id)
                   VALUES(%s,'profile',%s,%s) ON CONFLICT DO NOTHING""",
                (set_id, source["profile_id"], source["profile_variant_id"]),
            )
        await conn.execute("UPDATE default_sets SET updated_at=now() WHERE id=%s", (set_id,))
        return await get_set(conn, user_id, set_id), None
