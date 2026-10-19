"""End to end: /ai-condense suggests shrink-to-fit changes; /ai-condense/apply saves them in one revision."""

import os
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.ai_client import AiCompletion

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


@pytest.fixture()
def client(monkeypatch):
    name = f"condense_{uuid4().hex[:12]}"
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    base, _, _ = URL.rpartition("/")
    monkeypatch.setenv("DATABASE_URL", f"{base}/{name}")
    monkeypatch.delenv("STUDIOSHARE_DB_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")
    from app import ai_condense, ai_variants, main

    ai_condense.clear_cache()
    ai_variants.clear_cache()
    try:
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


def variant_row(variant_id):
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        return conn.execute("SELECT body, ai_generated FROM bullet_variants WHERE id=%s", (variant_id,)).fetchone()


def seeded(http):
    library = http.get("/api/library").json()
    if not library["compositions"]:
        http.post("/api/library/import-seed", json={"seed_key": "nia-calder-resume-v1"})
        library = http.get("/api/library").json()
    cid = library["compositions"][0]["id"]
    rows = http.get(f"/api/compositions/{cid}/bullet-placements").json()
    work = [row for row in rows if row["destination_section"] == "work_experience"]
    return cid, work


def test_condense_suggests_and_apply_saves_in_one_revision(client, monkeypatch):
    http = client
    cid, work = seeded(http)
    first = work[0]
    parents = list(dict.fromkeys(row["destination_parent_id"] for row in work))
    assert len(parents) >= 2, "seed needs two roles"
    keep_parent = first["destination_parent_id"]
    removable = next(
        row for row in work if row["destination_parent_id"] == keep_parent and row["id"] != first["id"]
    )
    original = first["wording_snapshot"]
    words = original.split()
    shorter = " ".join(words[: max(3, len(words) // 2)])
    sent = {}

    async def fake_complete(messages, schema, name):
        import json

        request = json.loads(messages[1]["content"])
        sent.update(request)
        ids = {row["text"]: row["id"] for row in request["bullets"]}
        entries = {row["entry"]: row["id"] for row in request["entries"]}
        return AiCompletion(
            {
                "condense": [{"id": ids[original], "body": shorter, "reason": "Tighter."}],
                "remove_bullets": [{"id": ids[removable["wording_snapshot"]], "reason": "Weakest."}],
                "remove_entries": [{"id": list(entries.values())[-1], "reason": "Least relevant."}],
            },
            "m:free",
        )

    monkeypatch.setattr("app.ai_condense.complete_json", fake_complete)
    monkeypatch.setattr("app.ai_condense.ai_available", lambda: True)
    line_id = f"{keep_parent}-bullet-0"
    response = http.post(
        f"/api/compositions/{cid}/ai-condense",
        json={"bullet_lines": {line_id: 3}, "chars_per_line": 40, "lines_over": 4},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["method"] == "ai", result
    assert sent["posting"].startswith("No job chosen")
    condense = next(item for item in result["items"] if item["kind"] == "condense")
    assert condense["id"] == first["id"] and condense["lines"] == 3 and condense["body"] == shorter
    entry = next(item for item in result["items"] if item["kind"] == "remove_entry")

    revision = http.get(f"/api/compositions/{cid}").json()["revision"]
    applied = http.post(
        f"/api/compositions/{cid}/ai-condense/apply",
        json={
            "revision": revision,
            "remove_bullets": [removable["id"]],
            "remove_entries": [entry["id"]],
            "rewrites": [{"placement_id": first["id"], "body": shorter, "name": "Condensed", "source": "draft"}],
        },
    )
    assert applied.status_code == 200, applied.text
    state = applied.json()
    assert state["revision"] == revision + 1
    rows = {row["id"]: row for row in http.get(f"/api/compositions/{cid}/bullet-placements").json()}
    assert removable["id"] not in rows
    assert rows[first["id"]]["wording_snapshot"] == shorter
    assert rows[first["id"]]["variant_id"] != first["variant_id"]
    assert entry["id"] not in [str(item["id"]) for item in state["resume"]["work_experience"]]
    # The library keeps the original wording; the condensed text is a new, AI-marked variant.
    assert variant_row(first["variant_id"]) == (original, False)
    assert variant_row(rows[first["id"]]["variant_id"]) == (shorter, True)

    stale = http.post(
        f"/api/compositions/{cid}/ai-condense/apply",
        json={"revision": revision, "remove_bullets": [first["id"]]},
    )
    assert stale.status_code == 409


def test_apply_rejects_conflicts_and_unknown_ids(client):
    http = client
    cid, work = seeded(http)
    revision = http.get(f"/api/compositions/{cid}").json()["revision"]
    both = http.post(
        f"/api/compositions/{cid}/ai-condense/apply",
        json={
            "revision": revision,
            "remove_bullets": [work[0]["id"]],
            "rewrites": [{"placement_id": work[0]["id"], "body": "Short"}],
        },
    )
    assert both.status_code == 422
    unknown = http.post(
        f"/api/compositions/{cid}/ai-condense/apply",
        json={"revision": revision, "remove_bullets": [str(uuid4())]},
    )
    assert unknown.status_code == 404
    empty = http.post(f"/api/compositions/{cid}/ai-condense/apply", json={"revision": revision})
    assert empty.status_code == 422


def test_one_line_variants_work_without_a_job_but_other_goals_need_one(client, monkeypatch):
    http = client
    cid, work = seeded(http)
    target = work[0]
    short = " ".join(target["wording_snapshot"].split()[:4])

    async def fake_complete(messages, schema, name):
        return AiCompletion({"drafts": [{"name": "One line", "body": short, "rationale": "Fits."}]}, "m:free")

    monkeypatch.setattr("app.ai_variants.complete_json", fake_complete)
    monkeypatch.setattr("app.ai_variants.ai_available", lambda: True)
    url = f"/api/compositions/{cid}/bullet-placements/{target['id']}/ai-variants"
    assert http.post(url, json={"goal": "concise"}).status_code == 422
    response = http.post(url, json={"goal": "one_line", "max_chars": 60})
    assert response.status_code == 200, response.text
    assert [item["body"] for item in response.json()["drafts"]] == [short]

    revision = http.get(f"/api/compositions/{cid}").json()["revision"]
    accepted = http.post(
        f"{url}/accept",
        json={"revision": revision, "name": "One line", "body": short, "source": "draft"},
    )
    assert accepted.status_code == 200, accepted.text
    rows = {row["id"]: row for row in http.get(f"/api/compositions/{cid}/bullet-placements").json()}
    assert variant_row(rows[target["id"]]["variant_id"]) == (short, True)
