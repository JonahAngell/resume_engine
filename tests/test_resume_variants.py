import os
from pathlib import Path
from uuid import uuid4
import psycopg
import pytest
from app.identity import CurrentUser
from app.library_repository import ensure_user
from app.library_service import import_seed
from app.editing_repository import create_composition
from app.resume_variants import (
    apply_library_defaults,
    attach_bullet,
    copy_resume_variant,
    detach_variant,
    save_as_resume_variant,
    save_bullet_edit,
)
from app.schemas import Resume
from async_test_utils import run_async

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


async def exercise():
    schema = f"variants_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        async with await psycopg.AsyncConnection.connect(
            URL, options=f"-c search_path={schema},public"
        ) as conn:
            for migration in sorted((ROOT / "backend/migrations").glob("*.sql")):
                await conn.execute(migration.read_text(encoding="utf-8"))
            user = await ensure_user(conn, CurrentUser("variants", "variants", "Variants", None))
            _, composition_id = await import_seed(
                conn, user["id"], ROOT / "seed/nia-calder-resume.json", "variants"
            )
            starter, error = await save_as_resume_variant(
                conn, user["id"], composition_id, "Site Reliability"
            )
            assert error is None and starter["is_starter"] and starter["is_default_starter"]
            original = (
                await (
                    await conn.execute(
                        """SELECT cb.id, cb.variant_id, v.body, c.revision
                           FROM composition_bullets cb
                           JOIN bullet_variants v ON v.id=cb.variant_id
                           JOIN resume_compositions c ON c.id=cb.composition_id
                           WHERE cb.composition_id=%s LIMIT 1""",
                        (composition_id,),
                    )
                ).fetchone()
            )
            saved, save_error = await save_bullet_edit(
                conn,
                user["id"],
                composition_id,
                original[0],
                original[3],
                "Tailored wording for this resume",
                "variant",
            )
            assert save_error is None and saved
            untouched = (
                await (
                    await conn.execute(
                        "SELECT body FROM bullet_variants WHERE id=%s", (original[1],)
                    )
                ).fetchone()
            )
            assert untouched[0] == original[2]
            copied = await copy_resume_variant(
                conn, user["id"], starter["id"], None, "", "", "", ""
            )
            assert copied and not copied["is_starter"]
            starter_after = (
                await (
                    await conn.execute(
                        "SELECT render_payload FROM resume_compositions WHERE id=%s",
                        (starter["id"],),
                    )
                ).fetchone()
            )
            assert starter_after[0] == starter["render_payload"]
            detached = await detach_variant(conn, user["id"], original[1])
            assert detached
            other = (
                await (
                    await conn.execute(
                        "SELECT id FROM bullets WHERE user_id=%s AND id<>%s AND archived_at IS NULL LIMIT 1",
                        (user["id"], detached["id"]),
                    )
                ).fetchone()
            )
            moved, attach_error = await attach_bullet(
                conn, user["id"], detached["id"], other[0]
            )
            assert attach_error is None and moved["id"] == str(other[0])
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_resume_variants_keep_the_original():
    run_async(exercise())


async def defaults_exercise():
    schema = f"defaults_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        async with await psycopg.AsyncConnection.connect(
            URL, options=f"-c search_path={schema},public"
        ) as conn:
            for migration in sorted((ROOT / "backend/migrations").glob("*.sql")):
                await conn.execute(migration.read_text(encoding="utf-8"))
            user = await ensure_user(conn, CurrentUser("defaults", "defaults", "Defaults", None))
            await import_seed(conn, user["id"], ROOT / "seed/nia-calder-resume.json", "defaults")
            created = await create_composition(
                conn,
                user["id"],
                "Defaults Check",
                "",
                Resume(header={"name": "Defaults"}),
                display_name="Defaults",
            )
            filled = await apply_library_defaults(conn, user["id"], created["id"])
            resume = filled["render_payload"]
            assert resume["summary"]
            assert resume["header"]["name"]
            assert resume["work_experience"] and resume["work_experience"][0]["bullets"]
            assert resume["education"] and resume["tool_groups"] and resume["personal_interests"]
            counts = await (
                await conn.execute(
                    """SELECT
                         (SELECT count(*) FROM composition_items WHERE composition_id=%s) items,
                         (SELECT count(*) FROM composition_bullets WHERE composition_id=%s) bullets""",
                    (created["id"], created["id"]),
                )
            ).fetchone()
            assert counts[0] > 0 and counts[1] > 0
            assert filled["profile_id"] and filled["summary_variant_id"]
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_new_resume_includes_library_defaults():
    run_async(defaults_exercise())
