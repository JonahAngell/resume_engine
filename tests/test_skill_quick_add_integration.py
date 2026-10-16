import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.identity import CurrentUser
from app.library_repository import add_skill_to_resume, ensure_user, load_skill_inputs
from app.library_service import import_seed
from app.resume_variants import save_as_resume_variant
from async_test_utils import run_async

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


async def fetch(conn, sql, params=()):
    return await (await conn.execute(sql, params)).fetchall()


async def snapshot(conn, cid):
    row = (await fetch(conn, "SELECT revision,render_payload FROM resume_compositions WHERE id=%s", (cid,)))[0]
    history = (await fetch(conn, "SELECT count(*) FROM composition_revisions WHERE composition_id=%s", (cid,)))[0][0]
    return row[0], row[1], history


def skills_of(payload):
    return {group["name"]: group["items"] for group in payload.get("tool_groups") or []}


async def exercise():
    schema = f"skills_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        async with await psycopg.AsyncConnection.connect(URL, options=f"-c search_path={schema},public") as conn:
            for migration in sorted((ROOT / "backend/migrations").glob("*.sql")):
                await conn.execute(migration.read_text(encoding="utf-8"))
            user = await ensure_user(conn, CurrentUser("skills", "skills", "Skills", None))
            uid = user["id"]
            _, cid = await import_seed(conn, uid, ROOT / "seed/jonah-resume.json", "skills")
            other, error = await save_as_resume_variant(conn, uid, cid, "Other resume")
            assert error is None
            oid = other["id"]

            inputs = await load_skill_inputs(conn, uid, cid)
            on_resume = [g for g in inputs["groups"] if g["on_resume"]]
            assert on_resume, "seed resume should include a Skills group"
            group = on_resume[0]
            other_shared = await fetch(
                conn,
                "SELECT 1 FROM composition_items WHERE composition_id=%s AND section='tool_groups' AND item_id=%s",
                (oid, group["id"]),
            )
            assert other_shared, "the copied resume should share the group"
            before_other = await snapshot(conn, oid)
            revision = (await snapshot(conn, cid))[0]

            # Stale revision: nothing is written.
            row, error = await add_skill_to_resume(conn, uid, cid, revision - 1 or 999, "Kubernetes", group["id"])
            assert (row, error) == (None, "stale")
            assert not await fetch(conn, "SELECT id FROM tools WHERE user_id=%s AND name='Kubernetes'", (uid,))

            # Adds to the library and this resume only.
            row, error = await add_skill_to_resume(conn, uid, cid, revision, "Kubernetes", group["id"])
            assert error is None and row["revision"] == revision + 1
            assert "Kubernetes" in skills_of(row["render_payload"])[group["name"]]
            tool_id = (await fetch(conn, "SELECT id FROM tools WHERE user_id=%s AND name='Kubernetes'", (uid,)))[0][0]
            assert await fetch(
                conn, "SELECT 1 FROM composition_hidden_tools WHERE composition_id=%s AND tool_id=%s", (oid, tool_id)
            )
            assert await snapshot(conn, oid) == before_other
            assert not await fetch(
                conn, "SELECT 1 FROM composition_hidden_tools WHERE composition_id=%s AND tool_id=%s", (cid, tool_id)
            )

            # Archived tool is restored, not duplicated, and still hidden elsewhere.
            await conn.execute("UPDATE tools SET archived_at=now() WHERE id=%s", (tool_id,))
            await conn.execute(
                "DELETE FROM composition_hidden_tools WHERE composition_id=%s AND tool_id=%s", (oid, tool_id)
            )
            revision = row["revision"]
            row, error = await add_skill_to_resume(conn, uid, cid, revision, "kubernetes", group["id"])
            assert error is None
            rows = await fetch(conn, "SELECT id,archived_at FROM tools WHERE user_id=%s AND lower(name)='kubernetes'", (uid,))
            assert rows == [(tool_id, None)]
            assert await fetch(
                conn, "SELECT 1 FROM composition_hidden_tools WHERE composition_id=%s AND tool_id=%s", (oid, tool_id)
            )

            # A tool active in another group is never moved; the chosen group gets its own row.
            second = next((g for g in inputs["groups"] if g["id"] != group["id"]), None)
            assert second, "seed should have more than one Skills group"
            revision = row["revision"]
            row, error = await add_skill_to_resume(conn, uid, cid, revision, "Kubernetes", second["id"])
            assert error is None
            rows = await fetch(conn, "SELECT group_id::text FROM tools WHERE user_id=%s AND name='Kubernetes' ORDER BY created_at", (uid,))
            assert [r[0] for r in rows] == [group["id"], second["id"]]

            # New group, and a newly added group shows only the added tool on this resume.
            await conn.execute(
                "INSERT INTO tool_groups(user_id,name,sort_order,archived_at) VALUES(%s,'Gadgets',99,now())", (uid,)
            )
            revision = row["revision"]
            row, error = await add_skill_to_resume(conn, uid, cid, revision, "Oscilloscope", None, "Gadgets")
            assert error is None
            assert skills_of(row["render_payload"])["Gadgets 2"] == ["Oscilloscope"]
            extra = (
                await fetch(conn, "INSERT INTO tool_groups(user_id,name,sort_order) VALUES(%s,'Extra',100) RETURNING id", (uid,))
            )[0][0]
            await conn.execute(
                "INSERT INTO tools(user_id,group_id,name,sort_order) VALUES(%s,%s,'Alpha',0),(%s,%s,'Beta',1)",
                (uid, extra, uid, extra),
            )
            revision = row["revision"]
            row, error = await add_skill_to_resume(conn, uid, cid, revision, "Gamma", extra)
            assert error is None
            assert skills_of(row["render_payload"])["Extra"] == ["Gamma"]
            assert await snapshot(conn, oid) == before_other

            # Another user's group is not found.
            stranger = await ensure_user(conn, CurrentUser("stranger", "stranger", "Stranger", None))
            foreign = (
                await fetch(conn, "INSERT INTO tool_groups(user_id,name,sort_order) VALUES(%s,'Theirs',0) RETURNING id", (stranger["id"],))
            )[0][0]
            row2, error = await add_skill_to_resume(conn, uid, cid, row["revision"], "Rust", foreign)
            assert (row2, error) == (None, "missing")
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_skill_quick_add_touches_only_this_resume():
    run_async(exercise())
