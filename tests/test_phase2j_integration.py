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
            parent, bullet, variant = await (
                await c.execute(
                    "SELECT x.id,b.id,v.id FROM content_items x JOIN bullets b ON b.parent_id=x.id JOIN bullet_variants v ON v.bullet_id=b.id WHERE x.user_id=%s ORDER BY x.id,b.id LIMIT 1",
                    (u["id"],),
                )
            ).fetchone()
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
