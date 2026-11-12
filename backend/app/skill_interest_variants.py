"""Variants of skill groups and interests.

A skill group variant has its own label and its own pick and order of the group's tools.
An interest variant is another wording of the interest. A resume chooses one through
``composition_items.variant_id``; NULL means the record itself.
"""

from uuid import UUID

from .editing_repository import many, one
from .library_repository import (
    _refresh_interest_compositions,
    _refresh_tool_compositions,
    _tool_groups_shown,
)
from .phase2j_repository import _lock_composition
from .resume_variants import _unique_name, rerender

KINDS = {
    "tool_group": {
        "table": "tool_group_variants",
        "parent": "tool_groups",
        "fk": "tool_group_id",
        "section": "tool_groups",
        "fields": "id,tool_group_id,name,group_name,tool_ids,is_default,sort_order,archived_at,created_at,updated_at",
    },
    "interest": {
        "table": "interest_variants",
        "parent": "interests",
        "fk": "interest_id",
        "section": "personal_interests",
        "fields": "id,interest_id,name,body,is_default,sort_order,archived_at,created_at,updated_at",
    },
}
SECTION_KINDS = {spec["section"]: kind for kind, spec in KINDS.items()}


async def _refresh(conn, user_id, kind, item_id):
    if kind == "tool_group":
        await _refresh_tool_compositions(conn, user_id, item_id, "skill-variant-update")
    else:
        await _refresh_interest_compositions(conn, user_id, item_id)


async def _check_tools(conn, user_id, group_id, tool_ids):
    """Keep only the group's own active tools, in the given order, without repeats."""
    rows = await many(
        conn,
        "SELECT id FROM tools WHERE group_id=%s AND user_id=%s AND archived_at IS NULL AND id=ANY(%s)",
        (group_id, user_id, list(tool_ids)),
    )
    valid = {row["id"] for row in rows}
    if any(tool_id not in valid for tool_id in tool_ids):
        return None
    seen: list[UUID] = []
    for tool_id in tool_ids:
        if tool_id not in seen:
            seen.append(tool_id)
    return seen


async def _set_default(conn, kind, variant):
    spec = KINDS[kind]
    await conn.execute(
        f"UPDATE {spec['table']} SET is_default=false,updated_at=now() WHERE {spec['fk']}=%s AND is_default AND id<>%s",
        (variant[spec["fk"]], variant["id"]),
    )
    await conn.execute(
        f"UPDATE {spec['table']} SET is_default=true,updated_at=now() WHERE id=%s",
        (variant["id"],),
    )


async def create_variant(conn, user_id, kind, item_id, data):
    """Add a variant. Returns (row, error) with error 'missing', 'name' or 'tools'."""
    spec = KINDS[kind]
    async with conn.transaction():
        parent = await one(
            conn,
            f"SELECT * FROM {spec['parent']} WHERE id=%s AND user_id=%s FOR UPDATE",
            (item_id, user_id),
        )
        if not parent:
            return None, "missing"
        name = (data.get("name") or "").strip()
        if await one(
            conn, f"SELECT id FROM {spec['table']} WHERE {spec['fk']}=%s AND name=%s", (item_id, name)
        ):
            return None, "name"
        if kind == "tool_group":
            tool_ids = await _check_tools(conn, user_id, item_id, data.get("tool_ids") or [])
            if tool_ids is None:
                return None, "tools"
            row = await one(
                conn,
                f"""INSERT INTO tool_group_variants(user_id,tool_group_id,name,group_name,tool_ids,sort_order)
                    VALUES(%s,%s,%s,%s,%s,
                      (SELECT COALESCE(max(sort_order)+1,0) FROM tool_group_variants WHERE tool_group_id=%s))
                    RETURNING {spec['fields']}""",
                (user_id, item_id, name, data["group_name"].strip(), tool_ids, item_id),
            )
        else:
            row = await one(
                conn,
                f"""INSERT INTO interest_variants(user_id,interest_id,name,body,sort_order)
                    VALUES(%s,%s,%s,%s,
                      (SELECT COALESCE(max(sort_order)+1,0) FROM interest_variants WHERE interest_id=%s))
                    RETURNING {spec['fields']}""",
                (user_id, item_id, name, data["body"].strip(), item_id),
            )
        if data.get("is_default"):
            await _set_default(conn, kind, row)
            row["is_default"] = True
        return row, None


async def _locked_variant(conn, user_id, kind, variant_id):
    spec = KINDS[kind]
    return await one(
        conn,
        f"SELECT {spec['fields']} FROM {spec['table']} WHERE id=%s AND user_id=%s FOR UPDATE",
        (variant_id, user_id),
    )


async def update_variant(conn, user_id, kind, variant_id, data):
    """Edit a variant's fields; any key left out of ``data`` stays as it is."""
    spec = KINDS[kind]
    async with conn.transaction():
        variant = await _locked_variant(conn, user_id, kind, variant_id)
        if not variant:
            return None, "missing"
        parent_id = variant[spec["fk"]]
        if data.get("name") is not None:
            name = data["name"].strip()
            if await one(
                conn,
                f"SELECT id FROM {spec['table']} WHERE {spec['fk']}=%s AND name=%s AND id<>%s",
                (parent_id, name, variant_id),
            ):
                return None, "name"
            variant["name"] = name
        if kind == "tool_group":
            if data.get("group_name") is not None:
                variant["group_name"] = data["group_name"].strip()
            if data.get("tool_ids") is not None:
                tool_ids = await _check_tools(conn, user_id, parent_id, data["tool_ids"])
                if tool_ids is None:
                    return None, "tools"
                variant["tool_ids"] = tool_ids
            await conn.execute(
                "UPDATE tool_group_variants SET name=%s,group_name=%s,tool_ids=%s,updated_at=now() WHERE id=%s",
                (variant["name"], variant["group_name"], variant["tool_ids"], variant_id),
            )
        else:
            if data.get("body") is not None:
                variant["body"] = data["body"].strip()
            await conn.execute(
                "UPDATE interest_variants SET name=%s,body=%s,updated_at=now() WHERE id=%s",
                (variant["name"], variant["body"], variant_id),
            )
        if data.get("is_default") is True:
            if variant["archived_at"]:
                return None, "archived"
            await _set_default(conn, kind, variant)
        elif data.get("is_default") is False:
            await conn.execute(
                f"UPDATE {spec['table']} SET is_default=false,updated_at=now() WHERE id=%s",
                (variant_id,),
            )
        await _refresh(conn, user_id, kind, parent_id)
        return await one(
            conn, f"SELECT {spec['fields']} FROM {spec['table']} WHERE id=%s", (variant_id,)
        ), None


async def set_archived(conn, user_id, kind, variant_id, archived):
    """Archive or restore a variant. Archiving also stops it being the default.

    Resumes already using an archived variant keep it; it just can't be chosen anew.
    """
    spec = KINDS[kind]
    async with conn.transaction():
        variant = await _locked_variant(conn, user_id, kind, variant_id)
        if not variant:
            return None
        if archived:
            sql = f"UPDATE {spec['table']} SET archived_at=COALESCE(archived_at,now()),is_default=false,updated_at=now() WHERE id=%s RETURNING {spec['fields']}"
        else:
            sql = f"UPDATE {spec['table']} SET archived_at=NULL,updated_at=now() WHERE id=%s RETURNING {spec['fields']}"
        return await one(conn, sql, (variant_id,))


async def pick_variant(conn, user_id, cid, revision, section, item_id, variant_id):
    """Choose which variant (or None for the record itself) a resume uses for one item."""
    kind = SECTION_KINDS.get(section)
    if not kind:
        return None, "missing"
    spec = KINDS[kind]
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
        if variant_id is not None:
            variant = await one(
                conn,
                f"SELECT id,archived_at FROM {spec['table']} WHERE id=%s AND {spec['fk']}=%s AND user_id=%s",
                (variant_id, item_id, user_id),
            )
            if not variant:
                return None, "missing"
            if variant["archived_at"] and variant["id"] != link["variant_id"]:
                return None, "archived"
        await conn.execute(
            "UPDATE composition_items SET variant_id=%s WHERE id=%s", (variant_id, link["id"])
        )
        return await rerender(conn, user_id, cid, f"{kind}-variant-pick"), None


async def save_tool_group(conn, user_id, cid, group_id, revision, mode, group_name, name=None):
    """Save a skill group's label and the tools this resume shows, in order.

    overwrite: update the variant the resume uses, or the group itself (label only; the
    resume's tool hiding and order stay on the resume). new: a new group holding copies of
    the shown tools, swapped into this resume. variant: a new variant of the group, chosen
    for this resume.
    """
    async with conn.transaction():
        locked, error = await _lock_composition(conn, user_id, cid, revision)
        if error:
            return None, error
        link = await one(
            conn,
            "SELECT id,variant_id FROM composition_items WHERE composition_id=%s AND section='tool_groups' AND item_id=%s",
            (cid, group_id),
        )
        if not link:
            return None, "missing"
        shown = (await _tool_groups_shown(conn, user_id, [group_id], cid))[0]
        if shown is None:
            return None, "missing"
        label = group_name.strip()
        tool_ids = [tool["id"] for tool in shown["tools"]]
        if mode == "overwrite":
            if link["variant_id"]:
                await conn.execute(
                    "UPDATE tool_group_variants SET group_name=%s,tool_ids=%s,updated_at=now() WHERE id=%s AND user_id=%s",
                    (label, tool_ids, link["variant_id"], user_id),
                )
            else:
                await conn.execute(
                    "UPDATE tool_groups SET name=%s,updated_at=now() WHERE id=%s AND user_id=%s",
                    (label, group_id, user_id),
                )
            # Other resumes that use this group (or variant) pick up the change too.
            await _refresh_tool_compositions(conn, user_id, group_id, "skill-save-overwrite")
        elif mode == "new":
            created = await one(
                conn,
                """INSERT INTO tool_groups(user_id,name,sort_order)
                   VALUES(%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM tool_groups WHERE user_id=%s))
                   RETURNING id""",
                (user_id, label, user_id),
            )
            for index, tool in enumerate(shown["tools"]):
                await conn.execute(
                    "INSERT INTO tools(user_id,group_id,name,sort_order) VALUES(%s,%s,%s,%s)",
                    (user_id, created["id"], tool["name"], index),
                )
            await conn.execute(
                "UPDATE composition_items SET item_id=%s,variant_id=NULL WHERE id=%s",
                (created["id"], link["id"]),
            )
            await conn.execute(
                """UPDATE composition_bullets SET destination_parent_id=%s,updated_at=now()
                   WHERE composition_id=%s AND destination_section='tool_groups' AND destination_parent_id=%s""",
                (created["id"], cid, group_id),
            )
        else:
            variant_name = (name or "").strip() or await _unique_name(
                conn,
                "SELECT id FROM tool_group_variants WHERE tool_group_id=%s AND name=%s",
                (group_id,),
                "Variant",
            )
            if await one(
                conn,
                "SELECT id FROM tool_group_variants WHERE tool_group_id=%s AND name=%s",
                (group_id, variant_name),
            ):
                return None, "name"
            variant = await one(
                conn,
                """INSERT INTO tool_group_variants(user_id,tool_group_id,name,group_name,tool_ids,sort_order)
                   VALUES(%s,%s,%s,%s,%s,
                     (SELECT COALESCE(max(sort_order)+1,0) FROM tool_group_variants WHERE tool_group_id=%s))
                   RETURNING id""",
                (user_id, group_id, variant_name, label, tool_ids, group_id),
            )
            await conn.execute(
                "UPDATE composition_items SET variant_id=%s WHERE id=%s", (variant["id"], link["id"])
            )
        return await rerender(conn, user_id, cid, f"skill-save-{mode}"), None


async def save_interest(conn, user_id, cid, interest_id, revision, mode, body, name=None):
    """Save an interest's wording: overwrite what the resume uses, a new interest, or a variant."""
    async with conn.transaction():
        locked, error = await _lock_composition(conn, user_id, cid, revision)
        if error:
            return None, error
        link = await one(
            conn,
            "SELECT id,variant_id FROM composition_items WHERE composition_id=%s AND section='personal_interests' AND item_id=%s",
            (cid, interest_id),
        )
        if not link:
            return None, "missing"
        text = body.strip()
        if mode == "overwrite":
            if link["variant_id"]:
                await conn.execute(
                    "UPDATE interest_variants SET body=%s,updated_at=now() WHERE id=%s AND user_id=%s",
                    (text, link["variant_id"], user_id),
                )
            else:
                await conn.execute(
                    "UPDATE interests SET body=%s,updated_at=now() WHERE id=%s AND user_id=%s",
                    (text, interest_id, user_id),
                )
            await _refresh_interest_compositions(conn, user_id, interest_id)
        elif mode == "new":
            created = await one(
                conn,
                """INSERT INTO interests(user_id,body,sort_order)
                   VALUES(%s,%s,(SELECT COALESCE(max(sort_order)+1,0) FROM interests WHERE user_id=%s))
                   RETURNING id""",
                (user_id, text, user_id),
            )
            await conn.execute(
                "UPDATE composition_items SET item_id=%s,variant_id=NULL WHERE id=%s",
                (created["id"], link["id"]),
            )
            await conn.execute(
                """UPDATE composition_bullets SET destination_parent_id=%s,updated_at=now()
                   WHERE composition_id=%s AND destination_section='personal_interests' AND destination_parent_id=%s""",
                (created["id"], cid, interest_id),
            )
        else:
            variant_name = (name or "").strip() or await _unique_name(
                conn,
                "SELECT id FROM interest_variants WHERE interest_id=%s AND name=%s",
                (interest_id,),
                "Variant",
            )
            if await one(
                conn,
                "SELECT id FROM interest_variants WHERE interest_id=%s AND name=%s",
                (interest_id, variant_name),
            ):
                return None, "name"
            variant = await one(
                conn,
                """INSERT INTO interest_variants(user_id,interest_id,name,body,sort_order)
                   VALUES(%s,%s,%s,%s,
                     (SELECT COALESCE(max(sort_order)+1,0) FROM interest_variants WHERE interest_id=%s))
                   RETURNING id""",
                (user_id, interest_id, variant_name, text, interest_id),
            )
            await conn.execute(
                "UPDATE composition_items SET variant_id=%s WHERE id=%s", (variant["id"], link["id"])
            )
        return await rerender(conn, user_id, cid, f"interest-save-{mode}"), None
