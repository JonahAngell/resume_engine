import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.editing_repository import (
    create_composition,
    duplicate,
    get_revision,
    update_composition_metadata,
)
from app.identity import CurrentUser
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
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_phase2g_integration():
    run_async(exercise())
