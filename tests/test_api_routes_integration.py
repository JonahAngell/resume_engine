"""Drive the real FastAPI app against a scratch schema: routes, 404 helpers and renders."""

import os
from urllib.parse import quote
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL is required")


@pytest.fixture
def client(monkeypatch):
    schema = f"api_{uuid4().hex}"
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
    joiner = "&" if "?" in URL else "?"
    monkeypatch.setenv("DATABASE_URL", f"{URL}{joiner}options={quote(f'-c search_path={schema},public')}")
    monkeypatch.delenv("STUDIOSHARE_DB_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    from app.main import app

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_routes_render_and_report_missing_records(client):
    missing = str(uuid4())
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/me").status_code == 200

    created = client.post("/api/library/items", json={"kind": "employment", "organization": "Acme", "title": "Analyst"})
    assert created.status_code == 201
    item_id = created.json()["id"]
    edited = client.put(f"/api/library/items/{item_id}", json={"kind": "employment", "organization": "Acme", "title": "Lead"})
    assert edited.status_code == 200 and edited.json()["id"] == item_id
    gone = client.put(f"/api/library/items/{missing}", json={"kind": "employment", "organization": "A", "title": "B"})
    assert gone.status_code == 404 and gone.json()["detail"] == "Historical item not found"

    assert client.put(f"/api/library/profiles/{missing}", json={"label": "x", "name": "x"}).status_code == 404
    assert client.post(f"/api/library/summary_variants/{missing}/archive").status_code == 404
    assert client.put("/api/library/summaries/order", json={"ids": [missing]}).status_code == 404
    assert client.get(f"/api/compositions/{missing}").status_code == 404

    seeded = client.post("/api/library/import-seed", json={"seed_key": "api-test"})
    assert seeded.status_code == 200
    cid = seeded.json()["composition_id"]
    composition = client.get(f"/api/compositions/{cid}")
    assert composition.status_code == 200
    rendered = client.get(f"/api/compositions/{cid}/render")
    assert rendered.status_code == 200 and "resume-page" in rendered.text
    revision = composition.json()["revision"]
    changed = client.put(
        f"/api/compositions/{cid}/preferences",
        json={"revision": revision, "preferred_page_length": 1, "template_style": "dais"},
    )
    assert changed.status_code == 200 and changed.json()["template_style"] == "dais"
    rendered = client.get(f"/api/compositions/{cid}/render")
    assert "font-family:'Tinos'" in rendered.text
    revisions = client.get(f"/api/compositions/{cid}/revisions").json()
    assert revisions
    first = revisions[0]["id"] if isinstance(revisions, list) else revisions["revisions"][0]["id"]
    assert client.get(f"/api/compositions/{cid}/revisions/{first}/render").status_code == 200
    assert client.get("/api/library").status_code == 200
