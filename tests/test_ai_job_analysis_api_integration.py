"""End to end: AI job analysis runs on request, is saved on the job, and feeds matching until the posting changes."""

import os
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")

POSTING = "Requirements:\n- Experience with SQL\n- Ability to turn complex analysis into clear insights for senior leaders\n"
INSIGHT = "Ability to turn complex analysis into clear insights for senior leaders"


class Completion:
    model = "test-model"

    def __init__(self, data):
        self.data = data


@pytest.fixture()
def client(monkeypatch):
    name = f"jobai_{uuid4().hex[:12]}"
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    base, _, _ = URL.rpartition("/")
    monkeypatch.setenv("DATABASE_URL", f"{base}/{name}")
    monkeypatch.delenv("STUDIOSHARE_DB_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    from app import ai_job_analysis, main

    calls = []

    async def fake_complete(messages, schema, name):
        calls.append(name)
        return Completion(
            {
                "requirements": [
                    {"source_span": "Experience with SQL", "group": "required", "category": "tool", "keywords": ["SQL"]},
                    {"source_span": INSIGHT, "group": "required", "category": "soft_skill", "keywords": ["clear insights for senior leaders"]},
                    {"source_span": "Kubernetes on call", "group": "required", "category": "tool", "keywords": ["Kubernetes"]},
                ]
            }
        )

    monkeypatch.setattr(ai_job_analysis, "complete_json", fake_complete)
    monkeypatch.setattr(ai_job_analysis, "ai_available", lambda: True)
    try:
        with TestClient(main.app) as test_client:
            test_client.ai_calls = calls
            yield test_client
    finally:
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


def test_analysis_runs_on_request_and_feeds_matching(client):
    job = client.post("/api/job-descriptions", json={"title": "Analyst", "body": POSTING}).json()
    assert job["ai_analysis"] is None
    assert client.ai_calls == []  # saving a job never calls the model

    result = client.post(f"/api/job-descriptions/{job['id']}/ai-analysis")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["status"] == "ok" and client.ai_calls == ["job_analysis"]
    assert body["job"]["ai_analysis"] == {
        "current": True,
        "model": "test-model",
        "analyzed_at": body["job"]["ai_analysis"]["analyzed_at"],
        "requirement_count": 2,  # the invented Kubernetes line was dropped
    }

    analysis = client.get(f"/api/job-descriptions/{job['id']}/analysis").json()
    added = next(row for row in analysis["required"] if row["text"] == INSIGHT)
    assert added["source"] == "ai" and added["ai_pending"] and added["weight"] == 0.5

    cid = client.post("/api/library/import-seed", json={"seed_key": "jobai-test"}).json()["composition_id"]
    match = client.post(f"/api/job-descriptions/{job['id']}/match", json={"composition_id": cid}).json()
    assert match["ai_pending_count"] == 1
    assert any(row["text"] == INSIGHT and row["ai_pending"] for row in match["required"])

    # Accepting is part of the job's keyword review.
    review = {**job["keyword_review"], "ai_accepted": [INSIGHT]}
    saved = client.put(f"/api/job-descriptions/{job['id']}", json={"title": "Analyst", "body": POSTING, "keyword_review": review})
    assert saved.status_code == 200, saved.text
    assert saved.json()["keyword_review"]["ai_accepted"] == [INSIGHT]
    match = client.post(f"/api/job-descriptions/{job['id']}/match", json={"composition_id": cid}).json()
    assert match["ai_pending_count"] == 0
    assert next(row for row in match["required"] if row["text"] == INSIGHT)["weight"] == 1.0


def test_editing_the_posting_retires_the_analysis(client):
    job = client.post("/api/job-descriptions", json={"title": "Analyst", "body": POSTING}).json()
    client.post(f"/api/job-descriptions/{job['id']}/ai-analysis")
    edited = client.put(f"/api/job-descriptions/{job['id']}", json={"title": "Analyst", "body": POSTING + "- Excel\n"}).json()
    assert edited["ai_analysis"]["current"] is False
    analysis = client.get(f"/api/job-descriptions/{job['id']}/analysis").json()
    assert all(row["source"] == "rules" for row in analysis["required"])


def test_unavailable_model_saves_nothing(client, monkeypatch):
    from app import ai_job_analysis

    monkeypatch.setattr(ai_job_analysis, "ai_available", lambda: False)
    job = client.post("/api/job-descriptions", json={"title": "Analyst", "body": POSTING}).json()
    result = client.post(f"/api/job-descriptions/{job['id']}/ai-analysis").json()
    assert result["status"] == "unavailable" and result["job"]["ai_analysis"] is None
    assert client.post(f"/api/job-descriptions/{uuid4()}/ai-analysis").status_code == 404
