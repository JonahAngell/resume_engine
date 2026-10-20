import asyncio
import json
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.identity import resolve_current_user


def request(cookie=None):
    headers = []
    if cookie:
        headers = [(b"cookie", f"access_token={cookie}".encode())]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/library",
            "raw_path": b"/api/library",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 1),
            "server": ("test", 443),
            "scheme": "https",
            "http_version": "1.1",
        }
    )


def run(coro):
    return asyncio.run(coro)


def test_local_identity_only_in_local(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    user = run(resolve_current_user(request(), None))
    assert user.external_id == "local-user"
    monkeypatch.setenv("APP_ENV", "studioshare")
    with pytest.raises(HTTPException) as caught:
        run(resolve_current_user(request(), None))
    assert caught.value.status_code == 401


def test_bearer_fallback_disabled_by_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "studioshare")
    monkeypatch.delenv("ALLOW_BEARER_AUTH", raising=False)
    with pytest.raises(HTTPException) as caught:
        run(resolve_current_user(request(), "Bearer secret-token"))
    assert caught.value.status_code == 401 and "secret-token" not in caught.value.detail


def test_cookie_resolves_documented_user(monkeypatch):
    monkeypatch.setenv("APP_ENV", "studioshare")
    monkeypatch.setenv("STUDIOSHARE_API_URL", "https://api.example")

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers):
            assert (
                url == "https://api.example/me"
                and headers["Authorization"] == "Bearer token-value"
            )
            return httpx.Response(
                200,
                json={
                    "id": "42",
                    "username": "jdoe",
                    "fullName": "J Doe",
                    "email": "j@example.test",
                },
            )

    with patch("app.identity.httpx.AsyncClient", return_value=Client()):
        user = run(resolve_current_user(request("token-value"), None))
    assert (user.external_id, user.username, user.display_name, user.email) == (
        "42",
        "jdoe",
        "J Doe",
        "j@example.test",
    )


@pytest.mark.parametrize("status_code", [401, 403])
def test_rejected_cookie_returns_401_without_token(monkeypatch, status_code):
    monkeypatch.setenv("APP_ENV", "studioshare")
    monkeypatch.setenv("STUDIOSHARE_API_URL", "https://api.example")

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            return httpx.Response(status_code)

    with patch("app.identity.httpx.AsyncClient", return_value=Client()):
        with pytest.raises(HTTPException) as caught:
            run(resolve_current_user(request("sensitive-token"), None))
    assert (
        caught.value.status_code == 401 and "sensitive-token" not in caught.value.detail
    )


def test_invalid_me_payload_fails_closed(monkeypatch):
    monkeypatch.setenv("APP_ENV", "studioshare")
    monkeypatch.setenv("STUDIOSHARE_API_URL", "https://api.example")

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            return httpx.Response(200, json={"username": "missing-id"})

    with patch("app.identity.httpx.AsyncClient", return_value=Client()):
        with pytest.raises(HTTPException) as caught:
            run(resolve_current_user(request("token"), None))
    assert caught.value.status_code == 502


def test_local_identity_refused_for_remote_database(monkeypatch):
    from app.identity import check_local_auth_safety

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@prod-db.example.com:5432/app")
    with pytest.raises(HTTPException) as caught:
        run(resolve_current_user(request(), None))
    assert caught.value.status_code == 503
    with pytest.raises(RuntimeError):
        check_local_auth_safety()
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db:5432/app")
    check_local_auth_safety()
    assert run(resolve_current_user(request(), None)).external_id == "local-user"


def test_identity_is_cached_per_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "studioshare")
    monkeypatch.setenv("STUDIOSHARE_API_URL", "https://api.example")
    calls = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers):
            calls.append(headers["Authorization"])
            return httpx.Response(200, json={"id": "7", "username": "a"})

    with patch("app.identity.httpx.AsyncClient", return_value=Client()):
        run(resolve_current_user(request("one"), None))
        run(resolve_current_user(request("one"), None))
        run(resolve_current_user(request("two"), None))
    assert calls == ["Bearer one", "Bearer two"]
