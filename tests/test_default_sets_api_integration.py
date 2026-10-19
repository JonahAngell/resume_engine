"""End to end: defaults sets build resumes from chosen records and wordings; AI recommend links a job."""

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.ai_client import AiCompletion

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")

JOB = """Senior Product Analyst

Required Qualifications
- Financial forecasting and SQL dashboards for venue staffing
"""


@pytest.fixture()
def client(monkeypatch):
    name = f"sets_{uuid4().hex[:12]}"
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    base, _, _ = URL.rpartition("/")
    monkeypatch.setenv("DATABASE_URL", f"{base}/{name}")
    monkeypatch.delenv("STUDIOSHARE_DB_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    from app import main

    try:
        with TestClient(main.app) as test_client:
            yield test_client, f"{base}/{name}"
    finally:
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


def seeded(http):
    http.post("/api/library/import-seed", json={"seed_key": "nia-calder-resume-v1"})
    return http.get("/api/library").json()


def entry_with_bullets(library):
    return next(item for item in library["employment"] if len({b["id"] for b in item["bullets"]}) >= 2)


def add_variant(http, bullet_id, body):
    response = http.post(f"/api/library/bullets/{bullet_id}/variants", json={"name": f"Alt {uuid4().hex[:4]}", "body": body})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def placements(http, cid):
    return http.get(f"/api/compositions/{cid}/bullet-placements").json()


def test_sets_choose_records_and_wording(client):
    http, _ = client
    library = seeded(http)
    entry = entry_with_bullets(library)
    bullet_ids = list(dict.fromkeys(b["id"] for b in entry["bullets"]))
    shared, only_a = bullet_ids[0], bullet_ids[1]
    alt = add_variant(http, shared, "Alternate wording for set B")

    a = http.post("/api/default-sets", json={"name": "Engineering"}).json()
    b = http.post("/api/default-sets", json={"name": "Management"}).json()
    assert a["is_default"] and not b["is_default"]
    assert http.post("/api/default-sets", json={"name": "engineering"}).status_code == 409

    def member(item_type, item_id, sets):
        response = http.put("/api/default-sets/memberships", json={
            "item_type": item_type, "item_id": item_id, "memberships": sets})
        assert response.status_code == 200, response.text

    member("content_item", entry["id"], [{"set_id": a["id"]}, {"set_id": b["id"]}])
    member("bullet", shared, [{"set_id": a["id"]}, {"set_id": b["id"], "variant_id": alt}])
    member("bullet", only_a, [{"set_id": a["id"]}])
    summary = library["summary_variants"][0]["id"]
    member("summary", summary, [{"set_id": b["id"]}])

    # A wording from another bullet is rejected.
    other_variant = next(r["variant_id"] for r in entry["bullets"] if r["id"] == only_a)
    bad = http.put("/api/default-sets/memberships", json={
        "item_type": "bullet", "item_id": shared,
        "memberships": [{"set_id": a["id"], "variant_id": other_variant}]})
    assert bad.status_code == 404

    lib = http.get("/api/library").json()
    assert {s["name"] for s in lib["default_sets"]} == {"Engineering", "Management"}
    assert sum(1 for m in lib["default_set_members"] if m["item_id"] == shared) == 2

    made_a = http.post("/api/compositions", json={"default_set_id": a["id"]}).json()
    made_b = http.post("/api/compositions", json={"default_set_id": b["id"]}).json()
    rows_a, rows_b = placements(http, made_a["id"]), placements(http, made_b["id"])
    assert {r["bullet_id"] for r in rows_a} == {shared, only_a}
    assert [r["bullet_id"] for r in rows_b] == [shared] and rows_b[0]["variant_id"] == alt
    assert made_b["resume"]["summary"] and not made_a["resume"]["summary"]
    assert [i["id"] for i in made_a["resume"]["work_experience"]] == [entry["id"]]
    assert made_a["resume"]["header"]["name"]

    # Without a set id the default set (Engineering) is used; entire_library ignores it.
    plain = http.post("/api/compositions", json={}).json()
    assert {r["bullet_id"] for r in placements(http, plain["id"])} == {shared, only_a}
    whole = http.post("/api/compositions", json={"entire_library": True}).json()
    assert len(placements(http, whole["id"])) > 2

    # A bullet whose entry is not in the set stays out.
    member("content_item", entry["id"], [{"set_id": a["id"]}])
    again_b = http.post("/api/compositions", json={"default_set_id": b["id"]}).json()
    assert placements(http, again_b["id"]) == []

    # Save a resume as a new set, then archive the default and see the default move.
    saved = http.post(f"/api/compositions/{whole['id']}/default-set", json={"name": "Everything"})
    assert saved.status_code == 201 and saved.json()["bullet_count"] == len(placements(http, whole["id"]))
    archived = http.post(f"/api/default-sets/{a['id']}/archive", json={"archived": True}).json()
    assert archived["archived_at"] and not archived["is_default"]
    sets = http.get("/api/default-sets").json()["sets"]
    assert sum(1 for s in sets if s["is_default"]) == 1


def test_starters_become_default_sets(client):
    http, database = client
    library = seeded(http)
    cid = library["compositions"][0]["id"]
    count = len(placements(http, cid))
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute("DELETE FROM default_sets")
        conn.execute("UPDATE resume_compositions SET is_starter=true,is_default_starter=true WHERE id=%s", (cid,))
        conn.execute("DELETE FROM schema_migrations WHERE name='026_default_sets.sql'")
        conn.execute("DROP TABLE default_set_members; DROP TABLE default_sets")
        conn.execute((ROOT / "backend/migrations/026_default_sets.sql").read_text())
    sets = http.get("/api/default-sets").json()["sets"]
    assert len(sets) == 1 and sets[0]["is_default"] and sets[0]["bullet_count"] == count
    assert all(c["id"] != cid for c in http.get("/api/library").json()["compositions"])
    made = http.post("/api/compositions", json={}).json()
    assert len(placements(http, made["id"])) == count


def test_ai_recommend_builds_linked_resume(client, monkeypatch):
    http, _ = client
    seeded(http)
    job = http.post("/api/job-descriptions", json={"company": "Parkline", "role": "Analyst", "body": JOB}).json()
    seen = {}

    async def fake_complete(messages, schema, name):
        seen["prompt"] = messages[1]["content"]
        import json

        request = json.loads(messages[1]["content"])
        first = request["entries"][0]
        return AiCompletion(
            {"entries": [{"key": first["key"], "bullets": [b["variants"][0]["key"] for b in first["bullets"][:2]],
                          "reason": "Closest match."}]},
            "m:free",
        )

    monkeypatch.setattr("app.ai_recommend.complete_json", fake_complete)
    monkeypatch.setattr("app.ai_recommend.ai_available", lambda: True)
    response = http.post("/api/compositions/ai-recommend", json={"job_description_id": job["id"]})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["status"] == "ok" and result["method"] == "ai" and result["entry_count"] == 1
    composition = result["composition"]
    assert composition["job_description_id"] == job["id"]
    assert composition["target_company"] == "Parkline" and composition["target_role"] == "Analyst"
    assert len(placements(http, composition["id"])) == result["bullet_count"] == 2
    revisions = http.get(f"/api/compositions/{composition['id']}/revisions").json()
    assert any(r.get("source") == "ai-recommendation" for r in revisions)
    missing = http.post("/api/compositions/ai-recommend", json={"job_description_id": str(uuid4())})
    assert missing.status_code == 404
