import os
from pathlib import Path
from uuid import uuid4
import psycopg, pytest
from app.identity import CurrentUser
from app.library_repository import (
    ensure_user,
    create_tool_group,
    create_tool,
    move_tool,
    restore_tool,
    select_tool_group,
)
from app.library_schemas import ToolGroupWrite, ToolWrite
from app.library_service import import_seed
from async_test_utils import run_async

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


async def exercise():
    schema = f"phase2b_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        async with await psycopg.AsyncConnection.connect(
            URL, options=f"-c search_path={schema},public"
        ) as conn:
            for migration in sorted((ROOT / "backend/migrations").glob("*.sql")):
                await conn.execute(migration.read_text(encoding="utf-8"))
            a = await ensure_user(conn, CurrentUser("p2b-a", "a", "A", None))
            b = await ensure_user(conn, CurrentUser("p2b-b", "b", "B", None))
            _, cid = await import_seed(
                conn, a["id"], ROOT / "seed/nia-calder-resume.json", "phase2b-seed"
            )
            count = (
                await (
                    await conn.execute(
                        "SELECT count(*) FROM composition_items WHERE composition_id=%s AND section IN ('tool_groups','projects','work_experience','leadership')",
                        (cid,),
                    )
                ).fetchone()
            )[0]
            assert count > 0
            g1 = await create_tool_group(conn, a["id"], ToolGroupWrite(name="Group A"))
            g2 = await create_tool_group(conn, a["id"], ToolGroupWrite(name="Group B"))
            tool = await create_tool(
                conn, a["id"], ToolWrite(name="Tool A", group_id=g1["id"])
            )
            assert await move_tool(conn, b["id"], tool["id"], g2["id"]) is None
            assert await move_tool(conn, a["id"], tool["id"], g2["id"])
            await conn.execute(
                "UPDATE tools SET archived_at=now() WHERE id=%s", (tool["id"],)
            )
            await conn.execute(
                "UPDATE tool_groups SET archived_at=now() WHERE id=%s", (g2["id"],)
            )
            row, error = await restore_tool(conn, a["id"], tool["id"], "require-parent")
            assert row is None and error == "parent"
            row, error = await restore_tool(conn, a["id"], tool["id"], "restore-parent")
            assert row and error is None
            comp = await (
                await conn.execute(
                    "SELECT revision FROM resume_compositions WHERE id=%s", (cid,)
                )
            ).fetchone()
            selected, error = await select_tool_group(
                conn, a["id"], cid, comp[0], g1["id"], True
            )
            assert selected and error is None
            stale, error = await select_tool_group(
                conn, a["id"], cid, comp[0], g2["id"], True
            )
            assert stale is None and error == "stale"
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_phase2b_integration():
    run_async(exercise())
