"""End to end: /ai-chat reads the resume, library and selected job, saves nothing, and its
proposals apply through the existing endpoints."""

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
OTHER_JOB = "Pastry Chef\n\nRequired Qualifications\n- Laminated dough experience"


@pytest.fixture()
def client(monkeypatch):
    name = f"chat_{uuid4().hex[:12]}"
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    base, _, _ = URL.rpartition("/")
    monkeypatch.setenv("DATABASE_URL", f"{base}/{name}")
    monkeypatch.delenv("STUDIOSHARE_DB_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")
    from app import ai_chat, main

    try:
        with TestClient(main.app) as test_client:
            yield test_client, ai_chat
    finally:
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


def _resume(http):
    library = http.get("/api/library").json()
    if not library["compositions"]:
        http.post("/api/library/import-seed", json={"seed_key": "nia-calder-resume-v1"})
        library = http.get("/api/library").json()
    return library["compositions"][0]["id"]


def test_chat_reads_only_the_selected_job_and_saves_nothing(client, monkeypatch):
    http, ai_chat = client
    cid = _resume(http)
    job = http.post("/api/job-descriptions", json={"company": "Parkline", "role": "Analyst", "body": JOB}).json()
    http.post("/api/job-descriptions", json={"company": "Bakery", "role": "Chef", "body": OTHER_JOB})
    placements = http.get(f"/api/compositions/{cid}/bullet-placements").json()
    target = next(row for row in placements if row["wording_snapshot"].startswith("Modeled attendance"))
    seen = {}

    async def fake_complete(messages, schema, name, **options):
        context = json.loads(messages[0]["content"].split("CONTEXT (JSON):\n", 1)[1])
        seen["context"] = context
        seen["options"] = options
        numbers = [item["number"] for item in context["resume"]["bullets"] if item["text"] == target["wording_snapshot"]]
        proposals = [{"kind": "remove", "bullet": number} for number in numbers]
        return AiCompletion({"reply": "Try this.", "proposals": proposals}, "openrouter/free")

    monkeypatch.setattr(ai_chat, "complete_json", fake_complete)
    before = http.get(f"/api/compositions/{cid}").json()["revision"]
    result = http.post(
        f"/api/compositions/{cid}/ai-chat",
        json={"job_id": job["id"], "messages": [{"role": "user", "content": "What should I cut?"}]},
    ).json()
    assert result["status"] == "ok", result
    assert seen["options"] == {"timeout": 60.0, "text_fallback": True}
    assert "Laminated" not in json.dumps(seen["context"])
    assert "financial forecasting" in seen["context"]["job"]["posting"]
    assert isinstance(seen["context"]["library"], list)
    assert http.get(f"/api/compositions/{cid}").json()["revision"] == before

    card = result["proposals"][0]
    assert card["placement_id"] == target["id"]
    removed = http.delete(f"/api/compositions/{cid}/bullet-placements/{card['placement_id']}?revision={before}")
    assert removed.status_code == 200, removed.text

    no_job = http.post(
        f"/api/compositions/{cid}/ai-chat", json={"job_id": None, "messages": [{"role": "user", "content": "Hi"}]}
    ).json()
    assert no_job["status"] == "ok" and seen["context"]["job"] is None


def test_chat_404s(client):
    http, _ = client
    cid = _resume(http)
    message = {"messages": [{"role": "user", "content": "Hi"}]}
    assert http.post(f"/api/compositions/{uuid4()}/ai-chat", json=message).status_code == 404
    assert http.post(f"/api/compositions/{cid}/ai-chat", json={**message, "job_id": str(uuid4())}).status_code == 404
    assert http.post(f"/api/compositions/{cid}/ai-chat", json={"messages": []}).status_code == 422
