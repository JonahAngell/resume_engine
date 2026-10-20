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
)
from app.editing_schemas import (
    BulletCreate,
    BulletPlacementReplace,
    BulletPlacementWrite,
    VariantWrite,
)
from app.phase2j_repository import insert_placement, replace_placement
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
                conn, a["id"], ROOT / "seed/nia-calder-resume.json", "2c"
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
            section = (
                await (
                    await conn.execute(
                        "SELECT section FROM composition_items WHERE composition_id=%s AND item_id=%s",
                        (cid, parent),
                    )
                ).fetchone()
            )[0]
            comp = await load_composition(conn, a["id"], cid)
            placed, error = await insert_placement(
                conn,
                a["id"],
                cid,
                BulletPlacementWrite(
                    revision=comp["revision"],
                    bullet_id=made["id"],
                    variant_id=made["variant_id"],
                    destination_section=section,
                    destination_parent_type="content_item",
                    destination_parent_id=parent,
                ),
            )
            assert placed and error is None
            placement_id = (
                await (
                    await conn.execute(
                        "SELECT id FROM composition_bullets WHERE composition_id=%s AND bullet_id=%s",
                        (cid, made["id"]),
                    )
                ).fetchone()
            )[0]
            comp = await load_composition(conn, a["id"], cid)
            choice = BulletPlacementReplace(
                revision=comp["revision"], bullet_id=made["id"], variant_id=alt["id"]
            )
            selected, error = await replace_placement(
                conn, a["id"], cid, placement_id, choice
            )
            assert selected and error is None
            stale, error = await replace_placement(
                conn, a["id"], cid, placement_id, choice
            )
            assert stale is None and error == "stale"
            row, error = await archive_variant(
                conn, a["id"], alt["id"], made["variant_id"]
            )
            assert row and error is None
            # Archiving a variant keeps the composition's pinned wording.
            snapshot = (
                await (
                    await conn.execute(
                        "SELECT variant_id,wording_snapshot FROM composition_bullets WHERE id=%s",
                        (placement_id,),
                    )
                ).fetchone()
            )
            assert snapshot == (alt["id"], "Short wording")
            assert await set_default_variant(conn, b["id"], made["variant_id"]) is None
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_phase2c_integration():
    run_async(exercise())
