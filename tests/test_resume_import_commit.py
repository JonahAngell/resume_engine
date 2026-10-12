import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.identity import CurrentUser
from app.library_repository import ensure_user, fetch_library
from app.resume_import import ImportDraft, ImportEntry, ImportProfile, ImportSummary, parse_upload
from app.resume_import_commit import commit_import
from async_test_utils import run_async

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


def _entry(section: str, included: bool = True, **kwargs) -> ImportEntry:
    base = dict(
        id=uuid4().hex,
        section=section,
        included=included,
        organization="",
        title="",
        institution="",
        bullets=[],
    )
    base.update(kwargs)
    return ImportEntry(**base)


async def apply_migrations(conn):
    for path in sorted((ROOT / "backend/migrations").glob("*.sql")):
        await conn.execute(path.read_text(encoding="utf-8"))


async def exercise():
    schema = f"import_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        options = f"-c search_path={schema},public"
        async with await psycopg.AsyncConnection.connect(URL, options=options) as conn:
            await apply_migrations(conn)
            user = await ensure_user(conn, CurrentUser("import-user", "import.user", "Jonah Angell", None))
            await conn.commit()
            library = await fetch_library(conn, user["id"])
            assert library["employment"] == []
            assert library["education"] == []
            preview = parse_upload(
                "Profile.csv",
                b"First Name,Last Name,Headline,Summary\nJonah,Angell,Data scientist,Hello\n",
            )
            assert preview.profile.name == "Jonah Angell"
            again = await fetch_library(conn, user["id"])
            assert again["employment"] == []
            assert again["compositions"] == []

            draft = ImportDraft(
                profile=ImportProfile(name="Jonah Angell", email="jonah@example.com"),
                summary=ImportSummary(included=False),
                entries=[
                    _entry(
                        "employment",
                        organization="Acme Corp",
                        title="Data Scientist",
                        bullets=["Built forecasting models"],
                        is_current=True,
                        start_year=2020,
                        start_month=1,
                    ),
                    _entry(
                        "employment",
                        included=False,
                        organization="Skipped Co",
                        title="Analyst",
                    ),
                    _entry("skip", included=True, organization="Also Skipped", title="Intern"),
                    _entry("education", institution="State University", graduation_year=2018),
                ],
            )
            result = await commit_import(conn, user["id"], draft, user["display_name"])
            saved = await fetch_library(conn, user["id"])
            employers = [item["organization"] for item in saved["employment"]]
            assert employers == ["Acme Corp"]
            assert [item["institution"] for item in saved["education"]] == ["State University"]
            payload = await (
                await conn.execute(
                    "SELECT render_payload FROM resume_compositions WHERE id=%s AND user_id=%s",
                    (result["composition_id"], user["id"]),
                )
            ).fetchone()
            resume = payload[0]
            assert [item["organization"] for item in resume["work_experience"]] == ["Acme Corp"]
            assert resume["work_experience"][0]["bullets"] == ["Built forecasting models"]
            assert resume["education"][0]["institution"].startswith("State University")
            assert "Skipped Co" not in str(resume)
            links = await (
                await conn.execute(
                    "SELECT section FROM composition_items WHERE composition_id=%s ORDER BY section",
                    (result["composition_id"],),
                )
            ).fetchall()
            assert {row[0] for row in links} == {"work_experience", "education"}
            duplicate = await commit_import(conn, user["id"], draft, user["display_name"])
            assert any("Acme Corp — Data Scientist is already in your library." == warning for warning in duplicate["warnings"])
            assert any("State University is already in your library." == warning for warning in duplicate["warnings"])
            after = await fetch_library(conn, user["id"])
            assert [item["organization"] for item in after["employment"]] == ["Acme Corp", "Acme Corp"]
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_preview_leaves_library_empty_and_commit_keeps_included_entries():
    run_async(exercise())
