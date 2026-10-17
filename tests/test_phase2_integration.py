import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.editing_repository import (
    get_revision,
    list_revisions,
    restore_revision,
    save_composition,
)
from app.identity import CurrentUser
from app.library_repository import (
    ensure_user,
    fetch_library,
    load_composition,
    search,
    set_archive,
)
from async_test_utils import run_async

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


PHASE1D = {
    "001_phase1b_master_library.sql",
    "002_phase1c_editing.sql",
    "003_phase1d_ownership_guards.sql",
}
PHASE2 = "004_phase2_historical_library.sql"


async def apply_migrations(conn, names=None, after=None):
    paths = sorted((ROOT / "backend/migrations").glob("*.sql"))
    if names is not None:
        paths = [path for path in paths if path.name in names]
    if after is not None:
        paths = [path for path in paths if path.name > after]
    for path in paths:
        await conn.execute(path.read_text(encoding="utf-8"))


async def seed_phase1d(conn, user_id, payload):
    """Library rows a Phase 1D user had, written with Phase 1D columns only.

    The current import_seed writes columns from later migrations, so it cannot run here.
    """
    header = payload["header"]
    await conn.execute(
        "INSERT INTO profiles(user_id,name,phone,email,linkedin_label,linkedin_url) VALUES(%s,%s,%s,%s,%s,%s)",
        (user_id, header["name"], header.get("phone", ""), header.get("email", ""),
         header.get("linkedin_label", ""), header.get("linkedin_url", "")),
    )
    summary_id = (
        await (
            await conn.execute(
                "INSERT INTO summary_variants(user_id,name,body,sort_order) VALUES(%s,'Seed summary',%s,0) RETURNING id",
                (user_id, payload["summary"]),
            )
        ).fetchone()
    )[0]
    return (
        await (
            await conn.execute(
                "INSERT INTO resume_compositions(user_id,name,summary_variant_id,render_payload) "
                "VALUES(%s,'Seed resume',%s,%s::jsonb) RETURNING id",
                (user_id, summary_id, json.dumps(payload)),
            )
        ).fetchone()
    )[0]


async def exercise_phase2():
    schema = f"phase2_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        options = f"-c search_path={schema},public"
        async with await psycopg.AsyncConnection.connect(URL, options=options) as conn:
            await apply_migrations(conn, PHASE1D)
            user_a = await ensure_user(
                conn, CurrentUser("phase2-a", "a", "User A", None)
            )
            user_b = await ensure_user(
                conn, CurrentUser("phase2-b", "b", "User B", None)
            )
            seed = json.loads((ROOT / "seed/jonah-resume.json").read_text(encoding="utf-8"))
            composition_id = await seed_phase1d(conn, user_a["id"], seed)

            # Read only columns available in the Phase 1D schema. The Phase 2
            # repository loader cannot be used until migration 004 adds description.
            before = await (
                await conn.execute(
                    "SELECT id, name, revision, render_payload, archived_at "
                    "FROM resume_compositions "
                    "WHERE id=%s AND user_id=%s AND archived_at IS NULL",
                    (composition_id, user_a["id"]),
                )
            ).fetchone()

            assert before is not None
            original_payload = before[3]

            # Apply Phase 2 to populated Phase 1D data and verify backfill compatibility.
            await apply_migrations(conn, {PHASE2})
            backfilled = await (
                await conn.execute(
                    "SELECT revision, snapshot FROM composition_revisions WHERE composition_id=%s",
                    (composition_id,),
                )
            ).fetchall()
            assert [row[0] for row in backfilled] == [1]
            assert backfilled[0][1]["resume"] == original_payload

            # The current repository code needs every later migration too.
            await apply_migrations(conn, after=PHASE2)
            after = await load_composition(conn, user_a["id"], composition_id)
            assert after["render_payload"] == original_payload
            migrated = await list_revisions(conn, user_a["id"], composition_id)
            assert [row["revision"] for row in migrated] == [1]
            migration_revision = await get_revision(
                conn, user_a["id"], composition_id, migrated[0]["id"]
            )
            assert migration_revision["snapshot"]["resume"] == original_payload

            # A successful save creates immutable history; a stale save changes nothing.
            changed = json.loads(json.dumps(original_payload))
            changed["summary"] = "Phase 2 integration summary"
            saved = await save_composition(
                conn, user_a["id"], composition_id, 1, changed, "integration"
            )
            assert saved["revision"] == 2
            assert (
                await save_composition(
                    conn, user_a["id"], composition_id, 1, original_payload, "stale"
                )
                is None
            )
            revisions = await list_revisions(conn, user_a["id"], composition_id)
            assert [row["revision"] for row in revisions] == [2, 1]

            # Restore creates revision 3 and preserves revisions 1 and 2.
            restored, error = await restore_revision(
                conn,
                user_a["id"],
                composition_id,
                migrated[0]["id"],
                2,
            )
            assert error is None
            assert restored["revision"] == 3
            assert restored["render_payload"] == original_payload
            assert [
                row["revision"]
                for row in await list_revisions(conn, user_a["id"], composition_id)
            ] == [3, 2, 1]

            # Stale and foreign restoration attempts must not mutate current state.
            stale, error = await restore_revision(
                conn,
                user_a["id"],
                composition_id,
                migrated[0]["id"],
                2,
            )
            assert stale is None and error == "stale"
            foreign, error = await restore_revision(
                conn,
                user_b["id"],
                composition_id,
                migrated[0]["id"],
                3,
            )
            assert foreign is None and error == "missing"
            current = await load_composition(conn, user_a["id"], composition_id)
            assert current["revision"] == 3

            # Search and archive operations remain scoped to the current user.
            own_results = await search(conn, user_a["id"], "Seed", "all", 50, 0)
            foreign_results = await search(conn, user_b["id"], "Seed", "all", 50, 0)
            assert any(row["type"] == "composition" for row in own_results)
            assert foreign_results == []
            summary_id = (await fetch_library(conn, user_a["id"]))["summary_variants"][
                0
            ]["id"]
            assert (
                await set_archive(
                    conn, user_b["id"], "summary_variants", summary_id, True
                )
                is None
            )
            assert await set_archive(
                conn, user_a["id"], "summary_variants", summary_id, True
            )
            archived = await search(conn, user_a["id"], "Seed", "archived", 50, 0)
            assert any(row["id"] == summary_id and row["archived"] for row in archived)
            assert await set_archive(
                conn, user_a["id"], "summary_variants", summary_id, False
            )

            # Database guards reject cross-user custom relationships and revisions.
            section_id = (
                await (
                    await conn.execute(
                        "INSERT INTO custom_sections(user_id,title,sort_order) "
                        "VALUES(%s,'Training',0) RETURNING id",
                        (user_a["id"],),
                    )
                ).fetchone()
            )[0]
            with pytest.raises(psycopg.Error):
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO custom_section_entries"
                        "(user_id,section_id,primary_text,sort_order) VALUES(%s,%s,'x',0)",
                        (user_b["id"], section_id),
                    )
            with pytest.raises(psycopg.Error):
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO composition_revisions"
                        "(composition_id,user_id,revision,snapshot) VALUES(%s,%s,99,'{}'::jsonb)",
                        (composition_id, user_b["id"]),
                    )
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_phase2_integration():
    run_async(exercise_phase2())
