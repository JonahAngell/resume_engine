import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.editing_repository import duplicate_variant, update_variant
from app.editing_schemas import VariantWrite
from app.identity import CurrentUser
from app.job_repository import create_job_description, load_variant_inputs
from app.job_schemas import JobDescriptionWrite
from app.library_repository import ensure_user
from app.library_service import import_seed
from app.resume_variants import save_as_resume_variant, save_bullet_edit
from async_test_utils import run_async

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


async def fetch(conn, sql, params=()):
    return await (await conn.execute(sql, params)).fetchall()


async def variant(conn, vid):
    return (
        await fetch(conn, "SELECT name,body,ai_generated,ai_model,ai_job_id FROM bullet_variants WHERE id=%s", (vid,))
    )[0]


async def exercise():
    schema = f"aivariants_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        async with await psycopg.AsyncConnection.connect(URL, options=f"-c search_path={schema},public") as conn:
            for migration in sorted((ROOT / "backend/migrations").glob("*.sql")):
                await conn.execute(migration.read_text(encoding="utf-8"))
            user = await ensure_user(conn, CurrentUser("aiv", "aiv", "AI Variants", None))
            uid = user["id"]
            _, cid = await import_seed(conn, uid, ROOT / "seed/nia-calder-resume.json", "aiv")
            other, _ = await save_as_resume_variant(conn, uid, cid, "Other resume")
            job, _ = await create_job_description(
                conn, uid, JobDescriptionWrite(company="Acme", role="Analyst", body="Financial forecasting experience.")
            )
            pid, bullet_id, original_variant, original_body = (
                await fetch(
                    conn,
                    """SELECT cb.id,cb.bullet_id,cb.variant_id,cb.wording_snapshot FROM composition_bullets cb
                       WHERE cb.composition_id=%s ORDER BY cb.sort_order,cb.id LIMIT 1""",
                    (cid,),
                )
            )[0]
            other_before = await fetch(
                conn, "SELECT wording_snapshot FROM composition_bullets WHERE composition_id=%s AND bullet_id=%s", (other["id"], bullet_id)
            )
            revision = (await fetch(conn, "SELECT revision FROM resume_compositions WHERE id=%s", (cid,)))[0][0]
            count = lambda: fetch(conn, "SELECT count(*) FROM bullet_variants WHERE bullet_id=%s", (bullet_id,))

            # The server reads the bullet from the placement.
            inputs, error = await load_variant_inputs(conn, uid, cid, pid, job["id"])
            assert error is None and inputs["original"] == original_body
            _, error = await load_variant_inputs(conn, uid, cid, uuid4(), job["id"])
            assert error == "placement"
            _, error = await load_variant_inputs(conn, uid, cid, pid, uuid4())
            assert error == "job"

            # Stale accept writes nothing.
            before = (await count())[0][0]
            row, error = await save_bullet_edit(
                conn, uid, cid, pid, revision + 5, "Drafted wording", "variant", name="Outcome first",
                ai={"generated": True, "model": "m:free", "job_id": job["id"]},
            )
            assert (row, error) == (None, "stale")
            assert (await count())[0][0] == before

            # Accept creates the variant and points this placement at it, in one revision.
            row, error = await save_bullet_edit(
                conn, uid, cid, pid, revision, "Drafted wording", "variant", name="Outcome first",
                ai={"generated": True, "model": "m:free", "job_id": job["id"]},
            )
            assert error is None and row["revision"] == revision + 1
            vid = (await fetch(conn, "SELECT variant_id FROM composition_bullets WHERE id=%s", (pid,)))[0][0]
            assert vid != original_variant
            assert await variant(conn, vid) == ("Outcome first", "Drafted wording", True, "m:free", job["id"])
            assert await fetch(
                conn, "SELECT wording_snapshot FROM composition_bullets WHERE composition_id=%s AND bullet_id=%s", (other["id"], bullet_id)
            ) == other_before

            # Name collision gets a suffix; edited and own provenance.
            row, _ = await save_bullet_edit(
                conn, uid, cid, pid, row["revision"], "Edited draft", "variant", name="Outcome first",
                ai={"generated": False, "model": "m:free", "job_id": job["id"]},
            )
            edited = (await fetch(conn, "SELECT variant_id FROM composition_bullets WHERE id=%s", (pid,)))[0][0]
            assert await variant(conn, edited) == ("Outcome first 2", "Edited draft", False, "m:free", job["id"])
            row, _ = await save_bullet_edit(conn, uid, cid, pid, row["revision"], "My own words", "variant", name="Mine")
            own = (await fetch(conn, "SELECT variant_id FROM composition_bullets WHERE id=%s", (pid,)))[0][0]
            assert await variant(conn, own) == ("Mine", "My own words", False, None, None)

            # Duplicate keeps the marker; rename keeps it; a body edit clears it but keeps history.
            copy = await duplicate_variant(conn, uid, vid)
            assert (await variant(conn, copy["id"]))[2:] == (True, "m:free", job["id"])
            await update_variant(conn, uid, vid, VariantWrite(name="Renamed", body="Drafted wording"))
            assert (await variant(conn, vid))[:3] == ("Renamed", "Drafted wording", True)
            await update_variant(conn, uid, vid, VariantWrite(name="Renamed", body="Changed by hand"))
            assert (await variant(conn, vid))[2:] == (False, "m:free", job["id"])

            # Overwrite-mode save clears the flag on the placed variant.
            await conn.execute("UPDATE composition_bullets SET variant_id=%s WHERE id=%s", (copy["id"], pid))
            revision = (await fetch(conn, "SELECT revision FROM resume_compositions WHERE id=%s", (cid,)))[0][0]
            await save_bullet_edit(conn, uid, cid, pid, revision, "Overwritten", "overwrite")
            assert (await variant(conn, copy["id"]))[2] is False

            # Deleting the job keeps the variant and clears the link.
            await conn.execute("UPDATE job_descriptions SET composition_id=NULL WHERE id=%s", (job["id"],))
            await conn.execute("UPDATE resume_compositions SET job_description_id=NULL WHERE user_id=%s", (uid,))
            await conn.execute("DELETE FROM job_descriptions WHERE id=%s", (job["id"],))
            assert (await variant(conn, edited))[4] is None

            # Another user cannot read this placement or job.
            stranger = await ensure_user(conn, CurrentUser("stranger", "stranger", "Stranger", None))
            _, error = await load_variant_inputs(conn, stranger["id"], cid, pid, uuid4())
            assert error == "resume"
    finally:
        async with await psycopg.AsyncConnection.connect(URL, autocommit=True) as admin:
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_ai_variant_accept_and_provenance():
    run_async(exercise())
