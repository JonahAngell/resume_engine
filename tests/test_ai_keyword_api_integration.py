"""End to end: /ai-keyword-assist issues revisions and new bullets; accepting saves them with provenance."""

import json
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
- Experience with financial forecasting for venue staffing
"""
KEYWORD = "Financial Forecasting"
REQUIREMENT = "Experience with financial forecasting for venue staffing"


@pytest.fixture()
def client(monkeypatch):
    name = f"keyword_{uuid4().hex[:12]}"
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    base, _, _ = URL.rpartition("/")
    monkeypatch.setenv("DATABASE_URL", f"{base}/{name}")
    monkeypatch.delenv("STUDIOSHARE_DB_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")
    from app import ai_keyword, ai_variants, main

    ai_keyword.clear_cache()
    ai_variants.clear_cache()
    try:
        with TestClient(main.app) as test_client:
            yield test_client, ai_keyword
    finally:
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


def provenance(body):
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        return conn.execute(
            "SELECT ai_generated, ai_model, ai_job_id::text FROM bullet_variants WHERE body=%s", (body,)
        ).fetchone()


def test_keyword_assist_revision_and_new_bullet(client, monkeypatch):
    http, ai_keyword = client
    library = http.get("/api/library").json()
    if not library["compositions"]:
        http.post("/api/library/import-seed", json={"seed_key": "nia-calder-resume-v1"})
        library = http.get("/api/library").json()
    cid = library["compositions"][0]["id"]
    job = http.post("/api/job-descriptions", json={"company": "Parkline", "role": "Analyst", "body": JOB}).json()
    placements = http.get(f"/api/compositions/{cid}/bullet-placements").json()
    target = next(row for row in placements if row["wording_snapshot"].startswith("Modeled attendance"))
    original = target["wording_snapshot"]
    revised = original.replace("Modeled attendance and staffing", "Built financial forecasting for attendance and staffing")
    fresh = "Turned staffing models into financial forecasting the board committee used each quarter"
    placeholder = "Used financial forecasting to plan venue staffing, saving [X hours] a season"

    async def fake_complete(messages, schema, name):
        sent = json.loads(messages[1]["content"])
        number = next(item["number"] for item in sent["bullets"] if item["text"] == original)
        entry = next(item["number"] for item in sent["entries"] if item["entry"].startswith("Data Analyst"))
        return AiCompletion(
            {
                "revisions": [{"bullet": number, "body": revised, "rationale": "Names the work."}],
                "new_bullets": [
                    {"entry": entry, "body": fresh, "rationale": "New evidence."},
                    {"entry": entry, "body": placeholder, "rationale": "Needs a number."},
                ],
                "no_fit_reason": "",
            },
            "openrouter/free",
        )

    monkeypatch.setattr(ai_keyword, "complete_json", fake_complete)
    result = http.post(
        f"/api/compositions/{cid}/ai-keyword-assist",
        json={"job_id": job["id"], "keyword": KEYWORD, "requirement": REQUIREMENT, "category": "domain"},
    ).json()
    assert result["status"] == "ok", result
    assert [card["placement_id"] for card in result["revisions"]] == [target["id"]]
    cards = {card["body"]: card for card in result["new_bullets"]}
    assert set(cards) == {fresh, placeholder} and cards[placeholder]["placeholders"]
    parent_id = cards[fresh]["parent_id"]

    revision = http.get(f"/api/compositions/{cid}").json()["revision"]
    accepted = http.post(
        f"/api/compositions/{cid}/bullet-placements/{target['id']}/ai-variants/accept",
        json={"revision": revision, "name": "Uses forecasting", "body": revised, "source": "draft", "job_id": job["id"]},
    )
    assert accepted.status_code == 200, accepted.text
    assert provenance(revised) == (True, "openrouter/free", job["id"])
    revision = accepted.json()["revision"]

    # Placeholders must be replaced first.
    blocked = http.post(
        f"/api/compositions/{cid}/ai-keyword-assist/accept-new",
        json={"revision": revision, "parent_id": parent_id, "body": placeholder, "source": "draft", "job_id": job["id"]},
    )
    assert blocked.status_code == 422

    # An unknown entry, or a library item that is not on this resume, is not found.
    missing = http.post(
        f"/api/compositions/{cid}/ai-keyword-assist/accept-new",
        json={"revision": revision, "parent_id": str(uuid4()), "body": fresh, "source": "draft", "job_id": job["id"]},
    )
    assert missing.status_code == 404

    added = http.post(
        f"/api/compositions/{cid}/ai-keyword-assist/accept-new",
        json={"revision": revision, "parent_id": parent_id, "body": fresh, "source": "draft", "job_id": job["id"], "model": "spoofed"},
    )
    assert added.status_code == 200, added.text
    assert provenance(fresh) == (True, "openrouter/free", job["id"])
    revision = added.json()["revision"]
    after = http.get(f"/api/compositions/{cid}/bullet-placements").json()
    assert any(row["wording_snapshot"] == fresh for row in after)

    # A filled-in placeholder is the user's edit: not AI-written, but the model is kept.
    filled = placeholder.replace("[X hours]", "about 180 crew hours")
    edited = http.post(
        f"/api/compositions/{cid}/ai-keyword-assist/accept-new",
        json={"revision": revision, "parent_id": parent_id, "body": filled, "source": "edited", "job_id": job["id"], "model": "openrouter/free"},
    )
    assert edited.status_code == 200, edited.text
    assert provenance(filled) == (False, "openrouter/free", job["id"])

    stale = http.post(
        f"/api/compositions/{cid}/ai-keyword-assist/accept-new",
        json={"revision": revision, "parent_id": parent_id, "body": "Own words about financial forecasting", "source": "own"},
    )
    assert stale.status_code == 409

    match = http.post(f"/api/job-descriptions/{job['id']}/match", json={"composition_id": cid})
    assert match.status_code == 200, match.text
    keywords = [item for row in match.json()["required"] for item in row["keywords"]]
    assert any(item["keyword"].lower() == "financial forecasting" and item["found"] for item in keywords)
