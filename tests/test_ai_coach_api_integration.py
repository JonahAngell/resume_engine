"""End to end: /ai-coach issues a rewrite, /accept saves it as an AI-written variant."""

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


@pytest.fixture()
def client(monkeypatch):
    name = f"coach_{uuid4().hex[:12]}"
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    base, _, _ = URL.rpartition("/")
    monkeypatch.setenv("DATABASE_URL", f"{base}/{name}")
    monkeypatch.delenv("STUDIOSHARE_DB_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")
    from app import ai_coach, main

    ai_coach.clear_cache()
    try:
        with TestClient(main.app) as test_client:
            yield test_client, ai_coach
    finally:
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


def test_coach_rewrite_accepted_unchanged_is_ai_written(client, monkeypatch):
    http, ai_coach = client
    library = http.get("/api/library").json()
    if not library["compositions"]:
        http.post("/api/library/import-seed", json={"seed_key": "nia-calder-resume-v1"})
        library = http.get("/api/library").json()
    cid = library["compositions"][0]["id"]
    job = http.post("/api/job-descriptions", json={"company": "Parkline", "role": "Analyst", "body": JOB}).json()
    placements = http.get(f"/api/compositions/{cid}/bullet-placements").json()
    target = next(row for row in placements if row["wording_snapshot"].startswith("Modeled attendance"))
    original = target["wording_snapshot"]
    proposed = original.replace("Modeled attendance and staffing", "Modeled attendance and staffing forecasts")

    async def fake_complete(messages, schema, name):
        bullets = __import__("json").loads(messages[1]["content"])["bullets"]
        number = next(item["number"] for item in bullets if item["text"] == original)
        return AiCompletion(
            {
                "suggestions": [
                    {"kind": "rewrite", "bullet": number, "requirement": "Experience with financial forecasting for venue staffing",
                     "keyword": "Financial Forecasting", "proposed": proposed, "rationale": "Uses the job's words.", "priority": "high"}
                ],
                "equivalents": [],
            },
            "openrouter/free",
        )

    monkeypatch.setattr(ai_coach, "complete_json", fake_complete)
    result = http.post(f"/api/job-descriptions/{job['id']}/ai-coach", json={"composition_id": cid}).json()
    assert result["status"] == "ok", result
    card = result["suggestions"][0]
    assert card["placement_id"] == target["id"] and card["proposed"] == proposed

    revision = http.get(f"/api/compositions/{cid}").json()["revision"]
    accepted = http.post(
        f"/api/compositions/{cid}/bullet-placements/{card['placement_id']}/ai-variants/accept",
        json={"revision": revision, "name": "Forecasting", "body": proposed, "source": "draft", "job_id": job["id"], "model": "spoofed"},
    )
    assert accepted.status_code == 200, accepted.text
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(
            "SELECT ai_generated, ai_model, ai_job_id::text FROM bullet_variants WHERE body=%s", (proposed,)
        ).fetchone()
    assert row == (True, "openrouter/free", job["id"])

    stale = http.post(
        f"/api/compositions/{cid}/bullet-placements/{card['placement_id']}/ai-variants/accept",
        json={"revision": revision, "name": "Again", "body": proposed, "source": "draft", "job_id": job["id"]},
    )
    assert stale.status_code == 409

    score = http.post(f"/api/job-descriptions/{job['id']}/ats-score", json={"composition_id": cid, "page_count": 1}).json()
    assert 0 <= score["score"] <= 100 and "not a guarantee" in score["disclaimer"]
