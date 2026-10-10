import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APP_ENV", "local")
sys.path.insert(0, str(ROOT / "backend"))

from app.main import app

client = TestClient(app)


def test_seed_and_render_contract():
    seed = client.get("/api/seed")
    assert seed.status_code == 200
    data = seed.json()
    assert data["header"]["name"] == "Jonah Angell"
    html = client.post("/api/render", json=data)
    assert html.status_code == 200
    assert "width: 8.5in" in html.text
    assert "height: 11in" in html.text
    assert 'data-section="work-experience"' in html.text
    assert data["summary"] in html.text


def test_schema_rejects_unknown_fields():
    data = client.get("/api/seed").json()
    data["unexpected"] = True
    assert client.post("/api/render", json=data).status_code == 422
