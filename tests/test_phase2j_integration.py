import os
from pathlib import Path
from uuid import uuid4
import psycopg, pytest
from app.identity import CurrentUser
from app.library_repository import ensure_user, load_composition
from app.library_service import import_seed
from app.phase2j_repository import (
    insert_placement,
    create_and_place,
    remove_placement,
    replace_placement,
    usage_rows,
)
from app.editing_schemas import (
    BulletPlacementWrite,
    BulletCreateAndPlace,
    BulletPlacementReplace,
)
from async_test_utils import run_async

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


async def exercise():
    schema = f"phase2j_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as a:
        await a.execute(f'CREATE SCHEMA "{schema}"')
    try:
        async with await psycopg.AsyncConnection.connect(
            URL, options=f"-c search_path={schema},public"
        ) as c:
            for m in sorted((ROOT / "backend/migrations").glob("*.sql")):
                await c.execute(m.read_text(encoding="utf-8"))
            u = await ensure_user(c, CurrentUser("2j-a", "a", "A", None))
            other = await ensure_user(c, CurrentUser("2j-b", "b", "B", None))
            _, cid = await import_seed(
                c, u["id"], ROOT / "seed/jonah-resume.json", "2j"
            )
            comp = await load_composition(c, u["id"], cid)
            # Seed bullets are already placed; place a fresh bullet on a seeded project.
            parent = (
                await (
                    await c.execute(
                        "SELECT id FROM content_items WHERE user_id=%s AND kind='project' ORDER BY sort_order LIMIT 1",
                        (u["id"],),
                    )
                ).fetchone()
            )[0]
            bullet = (
                await (
                    await c.execute(
                        "INSERT INTO bullets(user_id,parent_id,sort_order) VALUES (%s,%s,99) RETURNING id",
                        (u["id"], parent),
                    )
                ).fetchone()
            )[0]
            variant = (
                await (
                    await c.execute(
                        "INSERT INTO bullet_variants(user_id,bullet_id,name,body,is_default,sort_order) VALUES (%s,%s,'Phase 2j',%s,true,0) RETURNING id",
                        (u["id"], bullet, "Placed from the phase 2j picker."),
                    )
                ).fetchone()
            )[0]
            row, error = await insert_placement(
                c,
                u["id"],
                cid,
                BulletPlacementWrite(
                    revision=comp["revision"],
                    bullet_id=bullet,
                    variant_id=variant,
                    destination_section="projects",
                    destination_parent_type="content_item",
                    destination_parent_id=parent,
                ),
            )
            assert row and error is None
            placed_parent = next(
                x for x in row["render_payload"]["projects"] if x["id"] == str(parent)
            )
            assert placed_parent["bullets"][-1] == "Placed from the phase 2j picker."
            usages = await usage_rows(c, u["id"], cid)
            placed = usages[-1]
            assert placed["wording_snapshot"] and placed["usage_status"] == "current"
            foreign, error = await remove_placement(
                c, other["id"], cid, placed["id"], row["revision"]
            )
            assert foreign is None and error == "missing"
            removed, error = await remove_placement(
                c, u["id"], cid, placed["id"], row["revision"]
            )
            assert removed and error is None
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as a:
            await a.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_phase2j_integration():
    run_async(exercise())
