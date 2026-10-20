import httpx

from app.ai_client import AiCallError, ai_available, complete_json, model_name, providers
from async_test_utils import run_async

GATEWAY = "https://gateway.test"
GATEWAY_CHAT = f"{GATEWAY}/v1/chat/completions"
OIDC = "http://sidecar.test/oidc"


def _ok(model: str, content: str = '{"families": []}') -> httpx.Response:
    return httpx.Response(200, json={"model": model, "choices": [{"message": {"content": content}}]})


def _call(handler):
    transport = httpx.MockTransport(handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await complete_json(
                [{"role": "user", "content": "Review this posting."}],
                {"type": "object"},
                "job_review",
                client=client,
            )

    return run_async(run())


def _gateway(monkeypatch, token: str = "pulled-token", models: str = ""):
    monkeypatch.setenv("STUDIOSHARE_AI_GATEWAY_URL", GATEWAY + "/")
    if token:
        monkeypatch.setenv("STUDIOSHARE_OIDC_TOKEN", token)
    if models:
        monkeypatch.setenv("STUDIOSHARE_AI_MODELS", models)


def _openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")


def test_gateway_is_tried_before_openrouter(monkeypatch):
    _gateway(monkeypatch)
    _openrouter(monkeypatch)
    assert [p.name for p in providers()] == ["studioshare", "openrouter"]
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers["Authorization"]))
        return _ok("anthropic/claude-sonnet-4-6")

    result = _call(handler)
    assert result.model == "anthropic/claude-sonnet-4-6"
    assert seen == [(GATEWAY_CHAT, "Bearer pulled-token")]


def test_gateway_alone_makes_ai_available(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert not ai_available()
    _gateway(monkeypatch)
    assert ai_available()
    assert model_name() == "studioshare:anthropic/claude-sonnet-4-6"


def test_gateway_url_without_credentials_is_skipped(monkeypatch):
    _gateway(monkeypatch, token="")
    _openrouter(monkeypatch)
    assert [p.name for p in providers()] == ["openrouter"]


def test_expired_gateway_token_falls_back_to_openrouter(monkeypatch):
    _gateway(monkeypatch)
    _openrouter(monkeypatch)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "gateway.test":
            return httpx.Response(401, json={"error": "expired"})
        return _ok("meta/example:free")

    result = _call(handler)
    assert result.model == "meta/example:free"
    assert seen == [GATEWAY_CHAT, "https://openrouter.ai/api/v1/chat/completions"]


def test_gateway_tries_each_configured_model(monkeypatch):
    _gateway(monkeypatch, models="first/model, second/model")
    models = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = __import__("json").loads(request.content)["model"]
        models.append(model)
        if model == "first/model":
            return httpx.Response(403, json={"error": "no use permission"})
        return _ok(model)

    assert _call(handler).model == "second/model"
    assert models == ["first/model", "second/model"]


def test_last_failure_status_is_reported(monkeypatch):
    _gateway(monkeypatch)
    _openrouter(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "gateway.test":
            return httpx.Response(503)
        return httpx.Response(429, headers={"Retry-After": "0"})

    try:
        _call(handler)
    except AiCallError as exc:
        assert exc.status == "rate_limited"
    else:
        raise AssertionError("expected failure")


def test_sidecar_token_is_minted_once_and_cached(monkeypatch):
    _gateway(monkeypatch, token="")
    monkeypatch.setenv("STUDIOSHARE_OIDC_URL", OIDC)
    mints = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == OIDC:
            assert request.method == "POST"
            mints["n"] += 1
            return httpx.Response(200, json={"token": "minted", "expiresAt": "2999-01-01T00:00:00Z"})
        assert request.headers["Authorization"] == "Bearer minted"
        return _ok("anthropic/claude-sonnet-4-6")

    _call(handler)
    _call(handler)
    assert mints["n"] == 1


def test_sidecar_token_near_expiry_is_reminted(monkeypatch):
    _gateway(monkeypatch, token="")
    monkeypatch.setenv("STUDIOSHARE_OIDC_URL", OIDC)
    mints = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == OIDC:
            mints["n"] += 1
            return httpx.Response(200, json={"token": f"t{mints['n']}", "expiresAt": "2000-01-01T00:00:00Z"})
        return _ok("anthropic/claude-sonnet-4-6")

    _call(handler)
    _call(handler)
    assert mints["n"] == 2


def test_failed_mint_falls_back_to_openrouter(monkeypatch):
    _gateway(monkeypatch, token="")
    monkeypatch.setenv("STUDIOSHARE_OIDC_URL", OIDC)
    _openrouter(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == OIDC:
            return httpx.Response(500)
        assert request.url.host == "openrouter.ai"
        return _ok("meta/example:free")

    assert _call(handler).model == "meta/example:free"


def test_nothing_configured_is_unavailable_without_a_call(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no provider should be called")

    try:
        _call(handler)
    except AiCallError as exc:
        assert exc.status == "unavailable"
    else:
        raise AssertionError("expected unavailable")


def test_prose_from_the_gateway_then_openrouter_401_reports_invalid(monkeypatch):
    """The Studioshare log case: Sonnet answers in prose, a stale OpenRouter key answers 401."""
    _gateway(monkeypatch)
    _openrouter(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "gateway.test":
            return _ok("anthropic/claude-sonnet-4-6", "Here are a few ideas for your resume.")
        return httpx.Response(401, json={"error": "bad key"})

    try:
        _call(handler)
    except AiCallError as exc:
        assert exc.status == "invalid"
    else:
        raise AssertionError("expected AiCallError")


def test_text_fallback_returns_prose_instead_of_failing(monkeypatch):
    _gateway(monkeypatch)
    transport = httpx.MockTransport(lambda request: _ok("anthropic/claude-sonnet-4-6", "Plain answer, no JSON."))

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await complete_json(
                [{"role": "user", "content": "Hi"}], {"type": "object"}, "resume_chat", client=client, text_fallback=True
            )

    result = run_async(run())
    assert result.data == {"_text": "Plain answer, no JSON."}
    assert result.model == "anthropic/claude-sonnet-4-6"


def test_shared_client_is_reused_within_a_loop_and_replaced_across_loops():
    import asyncio

    from app.ai_client import close_shared_client, shared_client

    async def twice():
        first, second = shared_client(), shared_client()
        return first, second

    a, b = asyncio.run(twice())
    assert a is b
    c, _ = asyncio.run(twice())
    assert c is not a
    asyncio.run(close_shared_client())


def test_bounded_cache_drops_the_oldest_entry():
    from app.cache import BoundedCache

    cache = BoundedCache(2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert (cache.get("a"), cache.get("b"), cache.get("c"), len(cache)) == (None, 2, 3, 2)
    cache.clear()
    assert len(cache) == 0
