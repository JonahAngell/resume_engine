import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.identity import CurrentUser
from app.library_repository import ensure_user, set_tool_order, set_tool_visibility, update_tool_group
from app.library_schemas import ToolGroupWrite
from app.library_service import import_seed
from async_test_utils import run_async

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


async def payload(conn, cid):
    row = await (await conn.execute("SELECT revision,render_payload FROM resume_compositions WHERE id=%s", (cid,))).fetchone()
    return row[0], row[1]


async def exercise():
    schema = f"toolrender_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        async with await psycopg.AsyncConnection.connect(URL, options=f"-c search_path={schema},public") as conn:
            for migration in sorted((ROOT / "backend/migrations").glob("*.sql")):
                await conn.execute(migration.read_text(encoding="utf-8"))
            user = await ensure_user(conn, CurrentUser("tools", "tools", "Tools", None))
            uid = user["id"]
            _, cid = await import_seed(conn, uid, ROOT / "seed/nia-calder-resume.json", "tools")
            groups = await (
                await conn.execute(
                    """SELECT i.item_id FROM composition_items i WHERE i.composition_id=%s AND i.section='tool_groups'
                       ORDER BY i.sort_order,i.id""",
                    (cid,),
                )
            ).fetchall()
            group_ids = [g[0] for g in groups]
            target = None
            for gid in group_ids:
                tools = await (
                    await conn.execute(
                        "SELECT id,name FROM tools WHERE group_id=%s AND archived_at IS NULL ORDER BY sort_order,id", (gid,)
                    )
                ).fetchall()
                if len(tools) >= 3:
                    target = gid, tools
                    break
            assert target, "seed needs a skill group with three tools"
            gid, tools = target

            revision, _ = await payload(conn, cid)
            reversed_ids = [t[0] for t in reversed(tools)]
            _, error = await set_tool_order(conn, uid, cid, revision, gid, reversed_ids)
            assert error is None
            revision, _ = await payload(conn, cid)
            _, error = await set_tool_visibility(conn, uid, cid, revision, tools[0][0], False)
            assert error is None
            # A library-wide group edit re-renders every resume through the batched path.
            await update_tool_group(conn, uid, gid, ToolGroupWrite(name="Renamed group"))
            await conn.commit()

            _, rendered = await payload(conn, cid)
            position = group_ids.index(gid)
            group = rendered["tool_groups"][position]
            assert group["name"] == "Renamed group"
            assert group["items"] == [t[1] for t in reversed(tools)][:-1]
            assert len(rendered["tool_groups"]) == len(group_ids)
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_tool_group_render_respects_order_and_hidden_tools():
    run_async(exercise())
