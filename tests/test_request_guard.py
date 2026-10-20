from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_cross_site_write_is_blocked():
    r = client.post("/api/export/pdf", json={}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = client.post("/api/export/pdf", json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_same_origin_write_reaches_the_handler():
    r = client.post("/api/export/pdf", json={}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code != 403
    r = client.post("/api/export/pdf", json={}, headers={"Origin": "http://testserver"})
    assert r.status_code != 403


def test_oversized_body_is_rejected():
    r = client.post("/api/export/pdf", content=b"x" * (2 * 1024 * 1024 + 1), headers={"Content-Type": "application/json"})
    assert r.status_code == 413
