"""End to end: custom templates are saved per user, link to resumes, and shape preview, history and ATS."""

import os
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


@pytest.fixture()
def client(monkeypatch):
    name = f"templates_{uuid4().hex[:12]}"
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    base, _, _ = URL.rpartition("/")
    monkeypatch.setenv("DATABASE_URL", f"{base}/{name}")
    monkeypatch.delenv("STUDIOSHARE_DB_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    from app import main

    try:
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


def seeded(http) -> dict:
    cid = http.post("/api/library/import-seed", json={"seed_key": "templates-test"}).json()["composition_id"]
    return http.get(f"/api/compositions/{cid}").json()


def prefs(http, comp, **changes):
    body = {"revision": comp["revision"], "preferred_page_length": comp.get("preferred_page_length", 1), **changes}
    response = http.put(f"/api/compositions/{comp['id']}/preferences", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_options_and_create_with_base_defaults(client):
    listing = client.get("/api/templates").json()
    assert listing["templates"] == []
    assert {font["id"] for font in listing["options"]["fonts"]} >= {"arial", "lato", "inter", "source-serif"}
    assert listing["options"]["limits"]["margins.top"] == {"min": 0.3, "max": 1.25}

    made = client.post("/api/templates", json={"name": "Mine", "base_style": "dais"})
    assert made.status_code == 201, made.text
    template = made.json()
    assert template["settings"]["font"] == "tinos" and template["revision"] == 1
    assert client.post("/api/templates", json={"name": "mine", "base_style": "classic"}).status_code == 409
    bad = client.post("/api/templates", json={"name": "Bad", "base_style": "classic", "settings": {"margins": {"top": 3}}})
    assert bad.status_code == 422 and "margins.top" in bad.json()["detail"]
    assert client.post("/api/templates", json={"name": "Bad", "base_style": "classic", "settings": {"accent_color": "red"}}).status_code == 422


def test_linked_resume_renders_with_template_and_follows_edits(client):
    comp = seeded(client)
    template = client.post("/api/templates", json={"name": "Lato", "base_style": "classic", "settings": {"font": "lato"}}).json()

    linked = prefs(client, comp, template_style="sheets", template_id=template["id"])
    # A custom template renders on its own base style, whatever the request said.
    assert linked["template_id"] == template["id"] and linked["template_style"] == "classic"
    html = client.get(f"/api/compositions/{comp['id']}/render").text
    assert "custom-template" in html and "font-family:'Lato'" in html

    # A preferences save that leaves template_id out keeps the link.
    linked = prefs(client, linked, date_format="short", template_style="classic")
    assert linked["template_id"] == template["id"]

    before = linked["revision"]
    updated = client.put(
        f"/api/templates/{template['id']}",
        json={"revision": 1, "name": "Lato", "settings": {**template["settings"], "accent_color": "#aa0000"}, "composition_id": comp["id"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["template"]["revision"] == 2
    assert updated.json()["composition"]["revision"] == before + 1
    assert "#aa0000" in client.get(f"/api/compositions/{comp['id']}/render").text
    stale = client.put(f"/api/templates/{template['id']}", json={"revision": 1, "name": "Lato", "settings": template["settings"]})
    assert stale.status_code == 409

    history = client.get(f"/api/compositions/{comp['id']}/revisions").json()
    entry = next(item for item in history if item["source"] == "template-update")
    assert "Lato" in (entry["note"] or "")
    # The history entry keeps the look it had at that moment.
    assert "#aa0000" in client.get(f"/api/compositions/{comp['id']}/revisions/{entry['id']}/render").text
    assert client.get("/api/templates").json()["templates"][0]["used_by"] == 1


def test_tools_layout_override_and_ats_penalty(client):
    comp = seeded(client)
    assert "skill-table item" not in client.get(f"/api/compositions/{comp['id']}/render").text
    comp = prefs(client, comp, template_style="classic", tools_layout="table")
    assert comp["tools_layout"] == "table"
    assert "skill-table item" in client.get(f"/api/compositions/{comp['id']}/render").text
    comp = prefs(client, comp, template_style="sre", tools_layout="inline")
    assert "skill-table item" not in client.get(f"/api/compositions/{comp['id']}/render").text
    comp = prefs(client, comp, template_style="sre", tools_layout=None)
    assert "skill-table item" in client.get(f"/api/compositions/{comp['id']}/render").text

    job = client.post("/api/job-descriptions", json={"title": "Analyst", "company": "Acme", "body": "Required\n- SQL"})
    assert job.status_code in (200, 201), job.text
    score = client.post(f"/api/job-descriptions/{job.json()['id']}/ats-score", json={"composition_id": comp["id"], "page_count": 1})
    assert score.status_code == 200, score.text
    parsing = next(item for item in score.json()["components"] if item["id"] == "parsing")
    assert "table" in parsing["detail"]


def test_preview_delete_and_isolation(client):
    comp = seeded(client)
    template = client.post("/api/templates", json={"name": "Wide", "base_style": "classic"}).json()
    preview = client.post(
        "/api/templates/preview",
        json={"composition_id": comp["id"], "base_style": "classic", "settings": {"margins": {"top": 1.0, "bottom": 1.0}}},
    )
    assert preview.status_code == 200 and "--content-height: 9in" in preview.text

    comp = prefs(client, comp, template_style="classic", template_id=template["id"])
    deleted = client.delete(f"/api/templates/{template['id']}", params={"composition_id": comp["id"]})
    assert deleted.status_code == 200
    after = deleted.json()["composition"]
    assert after["template_id"] is None and after["revision"] == comp["revision"] + 1
    assert client.delete(f"/api/templates/{template['id']}").status_code == 404
    assert client.put(
        f"/api/compositions/{comp['id']}/preferences",
        json={"revision": after["revision"], "preferred_page_length": 1, "template_id": str(uuid4())},
    ).status_code == 404


def test_duplicate_and_restore_keep_the_template(client):
    comp = seeded(client)
    template = client.post("/api/templates", json={"name": "Keep", "base_style": "harvard"}).json()
    linked = prefs(client, comp, template_style="harvard", template_id=template["id"], tools_layout="table")
    copy = client.post(f"/api/compositions/{comp['id']}/duplicate", json={"name": "Copy of it"})
    assert copy.status_code in (200, 201), copy.text
    assert copy.json()["template_id"] == template["id"] and copy.json()["tools_layout"] == "table"

    history = client.get(f"/api/compositions/{comp['id']}/revisions").json()
    linked_rev = next(item for item in history if item["revision"] == linked["revision"])
    unlinked = prefs(client, linked, template_style="classic", template_id=None, tools_layout=None)
    assert unlinked["template_id"] is None
    restored = client.post(
        f"/api/compositions/{comp['id']}/revisions/{linked_rev['id']}/restore", json={"revision": unlinked["revision"]}
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["template_id"] == template["id"] and restored.json()["tools_layout"] == "table"
