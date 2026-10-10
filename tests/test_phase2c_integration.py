import os
from pathlib import Path
from uuid import uuid4
import psycopg, pytest
from app.identity import CurrentUser
from app.library_repository import ensure_user, load_composition
from app.library_service import import_seed
from app.editing_repository import (
    create_bullet,
    create_variant,
    set_default_variant,
    archive_variant,
    select_bullet_variant,
    render_historical,
)
from app.editing_schemas import BulletCreate, VariantWrite
from async_test_utils import run_async

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


async def exercise():
    schema = f"phase2c_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        async with await psycopg.AsyncConnection.connect(
            URL, options=f"-c search_path={schema},public"
        ) as conn:
            for m in sorted((ROOT / "backend/migrations").glob("*.sql")):
                await conn.execute(m.read_text(encoding="utf-8"))
            a = await ensure_user(conn, CurrentUser("2c-a", "a", "A", None))
            b = await ensure_user(conn, CurrentUser("2c-b", "b", "B", None))
            _, cid = await import_seed(
                conn, a["id"], ROOT / "seed/jonah-resume.json", "2c"
            )
            parent = (
                await (
                    await conn.execute(
                        "SELECT id FROM content_items WHERE user_id=%s ORDER BY id LIMIT 1",
                        (a["id"],),
                    )
                ).fetchone()
            )[0]
            made = await create_bullet(
                conn,
                a["id"],
                BulletCreate(
                    parent_id=parent, variant_name="Default", body="A wording"
                ),
            )
            assert (
                await create_bullet(
                    conn,
                    b["id"],
                    BulletCreate(parent_id=parent, variant_name="x", body="x"),
                )
                is None
            )
            alt = await create_variant(
                conn,
                a["id"],
                made["id"],
                VariantWrite(name="Short", body="Short wording"),
            )
            assert alt
            assert await set_default_variant(conn, a["id"], alt["id"])
            comp = await load_composition(conn, a["id"], cid)
            selected, error = await select_bullet_variant(
                conn, a["id"], cid, comp["revision"], made["id"], alt["id"]
            )
            assert selected and error is None
            stale, error = await select_bullet_variant(
                conn, a["id"], cid, comp["revision"], made["id"], alt["id"]
            )
            assert stale is None and error == "stale"
            row, error = await archive_variant(
                conn, a["id"], alt["id"], made["variant_id"]
            )
            assert row and error is None
            rendered = await render_historical(conn, a["id"], parent, cid)
            assert "Short wording" in rendered["bullets"]
            assert await set_default_variant(conn, b["id"], made["variant_id"]) is None
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_phase2c_integration():
    run_async(exercise())
