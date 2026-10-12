import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.editing_repository import (
    create_composition,
    duplicate,
    get_revision,
    restore_revision,
    update_composition_metadata,
)
from app.identity import CurrentUser
from app.job_repository import (
    archive_job_description,
    compare_job_description,
    create_job_description,
    update_job_description,
)
from app.job_schemas import JobDescriptionWrite
from app.library_repository import ensure_user, fetch_library
from app.schemas import Resume
from async_test_utils import run_async

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


async def exercise():
    schema = f"phase2g_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        async with await psycopg.AsyncConnection.connect(
            URL, options=f"-c search_path={schema},public"
        ) as conn:
            for migration in sorted((ROOT / "backend/migrations").glob("*.sql")):
                await conn.execute(migration.read_text(encoding="utf-8"))
            user = await ensure_user(conn, CurrentUser("2g-a", "a", "Test User", None))
            resume = Resume(header={"name": "Test User"})
            first = await create_composition(
                conn, user["id"], None, "", resume, display_name="Test User"
            )
            second = await create_composition(
                conn, user["id"], None, "", resume, display_name="Test User"
            )
            assert first["name"].startswith("Test User's Resume (")
            assert second["name"] == first["name"] + " (2)"
            changed, error = await update_composition_metadata(
                conn,
                user["id"],
                first["id"],
                first["revision"],
                "Internal",
                "",
                "Display",
                "Company",
                "Role",
            )
            assert error is None
            assert (
                changed["display_title"],
                changed["target_company"],
                changed["target_role"],
            ) == ("Display", "Company", "Role")
            revisions = await (
                await conn.execute(
                    "SELECT id FROM composition_revisions WHERE composition_id=%s ORDER BY revision DESC",
                    (first["id"],),
                )
            ).fetchall()
            snapshot = await get_revision(
                conn, user["id"], first["id"], revisions[0][0]
            )
            assert snapshot["snapshot"]["display_title"] == "Display"
            copy = await duplicate(conn, user["id"], first["id"], "Internal Copy")
            assert (
                copy["display_title"],
                copy["target_company"],
                copy["target_role"],
            ) == ("Display", "Company", "Role")
            summaries = (await fetch_library(conn, user["id"]))["compositions"]
            assert any(row["target_company"] == "Company" for row in summaries)
            job, error = await create_job_description(
                conn,
                user["id"],
                JobDescriptionWrite(
                    company="Acme",
                    role="Analyst",
                    title="Acme Analyst",
                    body="Required skills: Python",
                ),
            )
            other, error = await create_job_description(
                conn,
                user["id"],
                JobDescriptionWrite(
                    company="Other",
                    role="Engineer",
                    title="Other Engineer",
                    body="Required skills: SQL",
                ),
            )
            assert job and other and error is None
            linked, error = await update_composition_metadata(
                conn,
                user["id"],
                first["id"],
                changed["revision"],
                "Internal",
                "",
                "Display",
                job_description_id=job["id"],
                link_job=True,
            )
            assert error is None
            assert linked["job_description_id"] == job["id"]
            assert (linked["target_company"], linked["target_role"]) == ("Acme", "Analyst")
            link_revision = (
                await (
                    await conn.execute(
                        """SELECT id FROM composition_revisions
                           WHERE composition_id=%s AND source='metadata'
                           ORDER BY revision DESC LIMIT 1""",
                        (first["id"],),
                    )
                ).fetchone()
            )[0]
            copied = await duplicate(conn, user["id"], first["id"], "Linked Copy")
            assert copied["job_description_id"] == job["id"]
            revised, error = await update_job_description(
                conn,
                user["id"],
                job["id"],
                JobDescriptionWrite(
                    company="Acme Inc",
                    role="Data Analyst",
                    title="Acme Analyst",
                    body="Required skills: Python",
                ),
            )
            assert error is None and revised["company"] == "Acme Inc"
            stored = (
                await (
                    await conn.execute(
                        """SELECT target_company, target_role, revision, job_description_id
                           FROM resume_compositions WHERE id=%s""",
                        (first["id"],),
                    )
                ).fetchone()
            )
            assert stored == ("Acme Inc", "Data Analyst", linked["revision"], job["id"])
            compared, error = await compare_job_description(
                conn, user["id"], other["id"], first["id"]
            )
            assert error is None and compared["composition_id"] == first["id"]
            after_compare = (
                await (
                    await conn.execute(
                        """SELECT revision, job_description_id
                           FROM resume_compositions WHERE id=%s""",
                        (first["id"],),
                    )
                ).fetchone()
            )
            assert after_compare == (linked["revision"], job["id"])
            missing, error = await update_composition_metadata(
                conn,
                user["id"],
                first["id"],
                linked["revision"],
                "Internal",
                "",
                "Display",
                job_description_id=uuid4(),
                link_job=True,
            )
            assert missing is None and error == "job"
            await archive_job_description(conn, user["id"], job["id"])
            restored, error = await restore_revision(
                conn, user["id"], first["id"], link_revision, linked["revision"]
            )
            assert error is None
            assert restored["job_description_id"] is None
            assert (restored["target_company"], restored["target_role"]) == (
                "Acme",
                "Analyst",
            )
            kept, error = await update_composition_metadata(
                conn,
                user["id"],
                second["id"],
                second["revision"],
                second["name"],
                "",
                "",
                "Kept",
                "Kept",
            )
            assert error is None
            assert (kept["target_company"], kept["target_role"]) == ("Kept", "Kept")
            cleared, error = await update_composition_metadata(
                conn,
                user["id"],
                second["id"],
                kept["revision"],
                second["name"],
                "",
                "",
                job_description_id=None,
                link_job=True,
            )
            assert error is None
            assert cleared["job_description_id"] is None
            assert (cleared["target_company"], cleared["target_role"]) == ("", "")
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_phase2g_integration():
    run_async(exercise())
