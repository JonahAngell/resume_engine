"""End to end: /ai-variant-pick ranks library wording; replace-many switches placements in one revision."""

import os
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.ai_client import AiCompletion

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")

JOB = """Senior Product Analyst

Required Qualifications
- Financial forecasting and SQL dashboards for venue staffing
"""


@pytest.fixture()
def client(monkeypatch):
    name = f"pick_{uuid4().hex[:12]}"
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    base, _, _ = URL.rpartition("/")
    monkeypatch.setenv("DATABASE_URL", f"{base}/{name}")
    monkeypatch.delenv("STUDIOSHARE_DB_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")
    from app import ai_variant_pick, main

    ai_variant_pick.clear_cache()
    try:
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


def setup_resume(http):
    library = http.get("/api/library").json()
    if not library["compositions"]:
        http.post("/api/library/import-seed", json={"seed_key": "nia-calder-resume-v1"})
        library = http.get("/api/library").json()
    cid = library["compositions"][0]["id"]
    job = http.post("/api/job-descriptions", json={"company": "Parkline", "role": "Analyst", "body": JOB}).json()
    placements = http.get(f"/api/compositions/{cid}/bullet-placements").json()
    target = next(row for row in placements if row["destination_section"] == "work_experience")
    state = http.get(f"/api/compositions/{cid}").json()
    # A second wording of the same bullet, saved to the library as a variant.
    better = "Built financial forecasting SQL dashboards for venue staffing"
    saved = http.post(
        f"/api/compositions/{cid}/bullet-placements/{target['id']}/save",
        json={"revision": state["revision"], "mode": "variant", "body": better},
    )
    assert saved.status_code == 200, saved.text
    # Put the original wording back on the resume so the new variant is a library alternative.
    after = http.get(f"/api/compositions/{cid}/bullet-placements").json()
    placed = next(row for row in after if row["id"] == target["id"])
    restored = http.put(
        f"/api/compositions/{cid}/bullet-placements/{target['id']}",
        json={"revision": saved.json()["revision"], "bullet_id": target["bullet_id"], "variant_id": target["variant_id"]},
    )
    assert restored.status_code == 200, restored.text
    return cid, job["id"], target, placed["variant_id"], better


def test_pick_ranks_variants_and_replace_many_applies(client, monkeypatch):
    http = client
    cid, job_id, target, better_variant, better = setup_resume(http)

    async def fake_complete(messages, schema, name):
        return AiCompletion({"slots": []}, "m:free")

    monkeypatch.setattr("app.ai_variant_pick.complete_json", fake_complete)
    monkeypatch.setattr("app.ai_variant_pick.ai_available", lambda: True)
    response = http.post(f"/api/compositions/{cid}/ai-variant-pick", json={"job_id": job_id, "placement_ids": [target["id"]]})
    assert response.status_code == 200, response.text
    result = response.json()
    # The model scored nothing, so the keyword ranking stands in.
    assert result["status"] == "invalid" and result["method"] == "keywords"
    slot = result["slots"][0]
    assert slot["placement_id"] == target["id"]
    best = next(item for item in slot["candidates"] if item["key"] == slot["best_key"])
    assert slot["recommend"] and best["variant_id"] == better_variant and best["body"] == better

    everything = http.post(f"/api/compositions/{cid}/ai-variant-pick", json={"job_id": job_id, "use_ai": False}).json()
    assert len(everything["slots"]) > 1

    revision = http.get(f"/api/compositions/{cid}").json()["revision"]
    applied = http.post(
        f"/api/compositions/{cid}/bullet-placements/replace-many",
        json={
            "revision": revision,
            "items": [{"placement_id": target["id"], "bullet_id": best["bullet_id"], "variant_id": best["variant_id"]}],
        },
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["revision"] == revision + 1
    rows = http.get(f"/api/compositions/{cid}/bullet-placements").json()
    assert next(row for row in rows if row["id"] == target["id"])["wording_snapshot"] == better

    stale = http.post(
        f"/api/compositions/{cid}/bullet-placements/replace-many",
        json={
            "revision": revision,
            "items": [{"placement_id": target["id"], "bullet_id": target["bullet_id"], "variant_id": target["variant_id"]}],
        },
    )
    assert stale.status_code == 409


def test_replace_many_rejects_a_bullet_from_another_entry_or_duplicates(client):
    http = client
    cid = setup_resume(http)[0]
    rows = http.get(f"/api/compositions/{cid}/bullet-placements").json()
    work = [row for row in rows if row["destination_section"] == "work_experience"]
    first = work[0]
    other = next(row for row in work if row["destination_parent_id"] != first["destination_parent_id"])
    same = next(
        row for row in work if row["destination_parent_id"] == first["destination_parent_id"] and row["id"] != first["id"]
    )
    revision = http.get(f"/api/compositions/{cid}").json()["revision"]
    wrong_parent = http.post(
        f"/api/compositions/{cid}/bullet-placements/replace-many",
        json={"revision": revision, "items": [{"placement_id": first["id"], "bullet_id": other["bullet_id"], "variant_id": other["variant_id"]}]},
    )
    assert wrong_parent.status_code == 422
    duplicate = http.post(
        f"/api/compositions/{cid}/bullet-placements/replace-many",
        json={"revision": revision, "items": [{"placement_id": first["id"], "bullet_id": same["bullet_id"], "variant_id": same["variant_id"]}]},
    )
    assert duplicate.status_code == 409
