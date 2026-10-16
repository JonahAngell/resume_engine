import json
import os
import re
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from app.editing_schemas import BulletPlacementReplace
from app.identity import CurrentUser
from app.job_match import _bullet_candidates
from app.job_repository import _placed_bullets
from app.library_repository import ensure_user, load_composition
from app.library_service import import_seed
from app.phase2j_repository import replace_placement
from app.phase2m_repository import materialize_composition
from app.render import render_resume
from async_test_utils import run_async

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
SEED = ROOT / "seed/nia-calder-resume.json"
BACKFILL = ROOT / "backend/migrations/025_render_payload_entry_ids.sql"
SECTIONS = ("education", "tool_groups", "projects", "work_experience", "leadership")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


async def _render(c, user_id, cid):
    materialized, error = await materialize_composition(c, user_id, cid)
    assert error is None
    return render_resume(materialized["resume"], False, materialized["renderer_contract_version"])


async def _selected_ids(c, cid):
    rows = await (
        await c.execute(
            "SELECT section,item_id::text FROM composition_items WHERE composition_id=%s ORDER BY section,sort_order",
            (cid,),
        )
    ).fetchall()
    out = {}
    for section, item_id in rows:
        out.setdefault(section, []).append(item_id)
    return out


async def exercise():
    schema = f"seedids_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as a:
        await a.execute(f'CREATE SCHEMA "{schema}"')
    try:
        async with await psycopg.AsyncConnection.connect(
            URL, options=f"-c search_path={schema},public"
        ) as c:
            for m in sorted((ROOT / "backend/migrations").glob("*.sql")):
                await c.execute(m.read_text(encoding="utf-8"))
            u = await ensure_user(c, CurrentUser("seed-ids-a", "a", "A", None))
            _, cid = await import_seed(c, u["id"], SEED, "seed-ids")

            # Every payload entry carries the library id it was imported as.
            comp = await load_composition(c, u["id"], cid)
            payload = comp["render_payload"]
            selected = await _selected_ids(c, cid)
            for section in SECTIONS:
                assert [e.get("id") for e in payload[section]] == selected[section]
            assert [x["id"] for x in payload["personal_interest_items"]] == selected["personal_interests"]

            # Saving a new wording on a seeded placement reaches the rendered preview.
            async with c.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id,bullet_id,destination_parent_id::text parent,sort_order,wording_snapshot FROM composition_bullets WHERE composition_id=%s AND destination_section='work_experience' ORDER BY destination_parent_id,sort_order LIMIT 1",
                    (cid,),
                )
                placement = await cur.fetchone()
            wording = "Rebuilt the crew scheduling export into a checked weekly report."
            variant = (
                await (
                    await c.execute(
                        "INSERT INTO bullet_variants(user_id,bullet_id,name,body,is_default,sort_order) VALUES (%s,%s,'Alt',%s,false,1) RETURNING id",
                        (u["id"], placement["bullet_id"], wording),
                    )
                ).fetchone()
            )[0]
            before = await _render(c, u["id"], cid)
            assert placement["wording_snapshot"] in before and wording not in before
            row, error = await replace_placement(
                c,
                u["id"],
                cid,
                placement["id"],
                BulletPlacementReplace(
                    revision=comp["revision"], bullet_id=placement["bullet_id"], variant_id=variant
                ),
            )
            assert row and error is None
            after = await _render(c, u["id"], cid)
            assert wording in after and placement["wording_snapshot"] not in after
            line = re.search(
                rf'data-bullet-id="{placement["parent"]}-bullet-{placement["sort_order"]}">\s*{re.escape(wording)}',
                after,
            )
            assert line, "replaced wording should render under the placement's line id"

            # The job matcher's line ids address rendered bullets.
            rendered_ids = set(re.findall(r'data-bullet-id="([^"]+)"', after))
            assert not any(x.startswith("None-") for x in rendered_ids)
            line_ids = {x["line_id"] for x in _bullet_candidates(await _placed_bullets(c, u["id"], cid))}
            assert line_ids and line_ids <= rendered_ids

            # The backfill restores ids on payloads stored without them.
            other = await ensure_user(c, CurrentUser("seed-ids-b", "b", "B", None))
            _, legacy = await import_seed(c, other["id"], SEED, "seed-ids")
            expected = await _selected_ids(c, legacy)
            stripped = (await load_composition(c, other["id"], legacy))["render_payload"]
            for section in SECTIONS:
                for entry in stripped[section]:
                    entry.pop("id", None)
            stripped["personal_interest_items"] = []
            await c.execute(
                "UPDATE resume_compositions SET render_payload=%s::jsonb WHERE id=%s",
                (json.dumps(stripped), legacy),
            )
            untouched = (await load_composition(c, u["id"], cid))["render_payload"]
            await c.execute(BACKFILL.read_text(encoding="utf-8"))
            restored = (await load_composition(c, other["id"], legacy))["render_payload"]
            for section in SECTIONS:
                assert [e.get("id") for e in restored[section]] == expected[section]
            assert [x["id"] for x in restored["personal_interest_items"]] == expected["personal_interests"]
            # Payloads that already carried ids are left alone.
            assert (await load_composition(c, u["id"], cid))["render_payload"] == untouched
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as a:
            await a.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_seed_import_placement_change_renders():
    run_async(exercise())
