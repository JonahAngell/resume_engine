import os
from pathlib import Path
from uuid import uuid4
import psycopg, pytest
from app.identity import CurrentUser
from app.library_repository import (
    ensure_user,
    create_custom_section,
    create_custom_entry,
    save_sections_panel,
    load_composition,
)
from app.library_schemas import (
    CustomSectionWrite,
    CustomEntryWrite,
    CompositionSectionsWrite,
)
from app.library_service import import_seed
from async_test_utils import run_async

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


async def exercise():
    schema = f"phase2d_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as a:
        await a.execute(f'CREATE SCHEMA "{schema}"')
    try:
        async with await psycopg.AsyncConnection.connect(
            URL, options=f"-c search_path={schema},public"
        ) as c:
            for m in sorted((ROOT / "backend/migrations").glob("*.sql")):
                await c.execute(m.read_text(encoding="utf-8"))
            u = await ensure_user(c, CurrentUser("2d-a", "a", "A", None))
            other = await ensure_user(c, CurrentUser("2d-b", "b", "B", None))
            _, cid = await import_seed(
                c, u["id"], ROOT / "seed/nia-calder-resume.json", "2d"
            )
            section = await create_custom_section(
                c, u["id"], CustomSectionWrite(title="Certifications", layout="dated")
            )
            entry = await create_custom_entry(
                c,
                u["id"],
                CustomEntryWrite(
                    section_id=section["id"],
                    primary_text="Certification",
                    date_label="2026",
                ),
            )
            assert entry
            assert (
                await create_custom_entry(
                    c,
                    other["id"],
                    CustomEntryWrite(section_id=section["id"], primary_text="Foreign"),
                )
                is None
            )
            _, other_cid = await import_seed(
                c,
                other["id"],
                ROOT / "seed/nia-calder-resume.json",
                "2d-other",
            )
            with pytest.raises(psycopg.Error):
                async with c.transaction():
                    await c.execute(
                        """
                        INSERT INTO composition_custom_sections(
                            composition_id,
                            section_id,
                            sort_order
                        )
                        VALUES (%s, %s, 0)
                        """,
                        (other_cid, section["id"]),
                    )
            comp = await load_composition(c, u["id"], cid)
            order = [
                "summary",
                "education",
                "custom:" + str(section["id"]),
                "tools",
                "projects",
                "work_experience",
                "leadership",
                "personal_interests",
            ]
            row, error = await save_sections_panel(
                c,
                u["id"],
                cid,
                CompositionSectionsWrite(
                    revision=comp["revision"],
                    section_order=order,
                    interest_layout="compact",
                    included_builtin=[
                        "summary",
                        "education",
                        "tools",
                        "projects",
                        "work_experience",
                        "leadership",
                        "personal_interests",
                    ],
                    included_custom=[section["id"]],
                ),
            )
            assert row and error is None and row["revision"] == comp["revision"] + 1
            assert (
                row["render_payload"]["custom_sections"][0]["title"] == "Certifications"
            )
            stale, error = await save_sections_panel(
                c,
                u["id"],
                cid,
                CompositionSectionsWrite(
                    revision=comp["revision"],
                    section_order=order,
                    interest_layout="compact",
                    included_builtin=[],
                    included_custom=[],
                ),
            )
            assert stale is None and error == "stale"
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as a:
            await a.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_phase2d_integration():
    run_async(exercise())
