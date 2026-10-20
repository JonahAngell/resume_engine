import os
from pathlib import Path
from uuid import uuid4
import psycopg, pytest
from app.identity import CurrentUser
from app.library_repository import ensure_user, search, load_composition
from app.library_service import import_seed
from app.editing_repository import (
    create_composition,
    update_composition_metadata,
    set_composition_archive,
    duplicate,
    list_revisions,
)
from app.schemas import Resume
from async_test_utils import run_async

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


async def exercise():
    schema = f"phase2e_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as a:
        await a.execute(f'CREATE SCHEMA "{schema}"')
    try:
        async with await psycopg.AsyncConnection.connect(
            URL, options=f"-c search_path={schema},public"
        ) as c:
            for m in sorted((ROOT / "backend/migrations").glob("*.sql")):
                await c.execute(m.read_text(encoding="utf-8"))
            u = await ensure_user(c, CurrentUser("2e-a", "a", "A", None))
            other = await ensure_user(c, CurrentUser("2e-b", "b", "B", None))
            _, cid = await import_seed(
                c, u["id"], ROOT / "seed/nia-calder-resume.json", "2e"
            )
            assert any(
                x["type"] == "tool"
                for x in await search(c, u["id"], "Python", "all", 50, 0)
            )
            assert await search(c, other["id"], "Python", "all", 50, 0) == []
            blank = await create_composition(
                c, u["id"], "Blank", "Description", Resume(header={"name": "A"})
            )
            assert (
                blank["revision"] == 1
                and len(await list_revisions(c, u["id"], blank["id"])) == 1
            )
            changed, error = await update_composition_metadata(
                c, u["id"], blank["id"], 1, "Renamed", "Changed"
            )
            assert changed and error is None
            stale, error = await update_composition_metadata(
                c, u["id"], blank["id"], 1, "No", "No"
            )
            assert stale is None and error == "stale"
            archived, error = await set_composition_archive(
                c, u["id"], blank["id"], changed["revision"], True
            )
            assert archived["archived_at"] and error is None
            restored, error = await set_composition_archive(
                c, u["id"], blank["id"], archived["revision"], False
            )
            assert restored and error is None
            source = await load_composition(c, u["id"], cid)
            copy = await duplicate(c, u["id"], cid, "Copy")
            assert (
                copy["render_payload"] == source["render_payload"]
                and len(await list_revisions(c, u["id"], copy["id"])) == 1
            )
            for table in [
                "composition_items",
                "composition_bullets",
                "composition_custom_sections",
            ]:
                src = (
                    await (
                        await c.execute(
                            f"SELECT count(*) FROM {table} WHERE composition_id=%s",
                            (cid,),
                        )
                    ).fetchone()
                )[0]
                dst = (
                    await (
                        await c.execute(
                            f"SELECT count(*) FROM {table} WHERE composition_id=%s",
                            (copy["id"],),
                        )
                    ).fetchone()
                )[0]
                assert src == dst
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as a:
            await a.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_phase2e_integration():
    run_async(exercise())
