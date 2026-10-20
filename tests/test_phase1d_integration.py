import json, os
from pathlib import Path
from uuid import uuid4
import pytest
import psycopg
from psycopg.rows import dict_row
from app.editing_repository import duplicate, save_composition, update_item
from app.editing_schemas import HistoricalItemWrite
from app.identity import CurrentUser
from app.library_repository import ensure_user, fetch_library, load_composition
from app.library_service import import_seed
from async_test_utils import run_async

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


async def exercise():
    schema = f"phase1d_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        async with await psycopg.AsyncConnection.connect(
            URL, options=f"-c search_path={schema},public"
        ) as conn:
            for migration in sorted((ROOT / "backend/migrations").glob("*.sql")):
                await conn.execute(migration.read_text(encoding="utf-8"))
            a = await ensure_user(conn, CurrentUser("a", "a", "User A", None))
            b = await ensure_user(conn, CurrentUser("b", "b", "User B", None))
            assert a["id"] != b["id"]
            imported, cid = await import_seed(
                conn, a["id"], ROOT / "seed/nia-calder-resume.json", "same-key"
            )
            assert imported
            assert (await fetch_library(conn, b["id"]))["compositions"] == []
            imported_b, cid_b = await import_seed(
                conn, b["id"], ROOT / "seed/nia-calder-resume.json", "same-key"
            )
            assert imported_b and cid_b != cid
            assert await load_composition(conn, b["id"], cid) is None
            row = await load_composition(conn, a["id"], cid)
            payload = row["render_payload"]
            assert await save_composition(conn, b["id"], cid, 1, payload) is None
            assert await duplicate(conn, b["id"], cid, "stolen") is None
            item = (
                await (
                    await conn.execute(
                        "SELECT id FROM content_items WHERE user_id=%s ORDER BY id LIMIT 1",
                        (a["id"],),
                    )
                ).fetchone()
            )[0]
            write = HistoricalItemWrite(
                kind="project", name="changed", date_label="2026", bullets=[]
            )
            assert await update_item(conn, b["id"], item, write) is None
            saved = await save_composition(conn, a["id"], cid, 1, payload)
            assert saved["revision"] == 2
            assert await save_composition(conn, a["id"], cid, 1, payload) is None
            bullet = (
                await (
                    await conn.execute(
                        "SELECT id FROM bullets WHERE user_id=%s LIMIT 1", (a["id"],)
                    )
                ).fetchone()
            )[0]
            with pytest.raises(psycopg.Error):
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO bullet_variants(user_id,bullet_id,name,body,sort_order) VALUES(%s,%s,'cross-user','x',1)",
                        (b["id"], bullet),
                    )
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_cross_user_isolation():
    run_async(exercise())
