"""Chat client for optional AI features.

Providers are tried in order: the Studioshare AI Gateway when the app runs on
Launch (or has `launch env pull` credentials), then free OpenRouter models.
"""

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime

import httpx

logger = logging.getLogger("resume_engine.ai")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("resume_engine.ai %(message)s"))
    logger.addHandler(_handler)
logger.propagate = False

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/free"
DEFAULT_GATEWAY_MODELS = ("anthropic/claude-sonnet-4-6",)
TOKEN_REFRESH_MARGIN = 300.0
TOKEN_FALLBACK_TTL = 600.0
PROMPT_VERSION = "1"
TIMEOUT_SECONDS = 30.0
MAX_RETRY_WAIT = 5.0

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class AiCallError(Exception):
    def __init__(self, status: str):
        self.status = status
        super().__init__(status)


@dataclass
class AiCompletion:
    data: dict
    model: str


@dataclass(frozen=True)
class Provider:
    name: str
    url: str
    models: tuple[str, ...]


def openrouter_model() -> str:
    return os.environ.get("OPENROUTER_MODEL", "").strip() or DEFAULT_MODEL


def api_key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", "").strip()


def is_free_model(model: str) -> bool:
    return model == DEFAULT_MODEL or model.endswith(":free")


def gateway_url() -> str:
    return os.environ.get("STUDIOSHARE_AI_GATEWAY_URL", "").strip().rstrip("/")


def gateway_models() -> tuple[str, ...]:
    raw = os.environ.get("STUDIOSHARE_AI_MODELS", "")
    models = tuple(part.strip() for part in raw.split(",") if part.strip())
    return models or DEFAULT_GATEWAY_MODELS


def _gateway_credentials() -> bool:
    return bool(
        os.environ.get("STUDIOSHARE_OIDC_TOKEN", "").strip()
        or os.environ.get("STUDIOSHARE_OIDC_URL", "").strip()
    )


def providers() -> list[Provider]:
    """Configured providers in the order they are tried."""
    found = []
    if gateway_url() and _gateway_credentials():
        found.append(Provider("studioshare", f"{gateway_url()}/v1/chat/completions", gateway_models()))
    model = openrouter_model()
    if api_key() and is_free_model(model):
        found.append(Provider("openrouter", OPENROUTER_URL, (model,)))
    return found


def ai_available() -> bool:
    return bool(providers())


def model_name() -> str:
    """Stable label for the provider chain. Callers use it in cache keys."""
    chain = providers()
    if not chain:
        return openrouter_model()
    return "|".join(f"{p.name}:{','.join(p.models)}" for p in chain)


_TOKEN: dict = {"value": "", "expires": 0.0}


def _expires_at(raw) -> float:
    try:
        stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return time.time() + TOKEN_FALLBACK_TTL
    return stamp.timestamp()


def clear_gateway_token() -> None:
    _TOKEN.update(value="", expires=0.0)


async def gateway_token(client: httpx.AsyncClient) -> str:
    """App-scoped OIDC token: the `launch env pull` token, else one minted by the sidecar."""
    pulled = os.environ.get("STUDIOSHARE_OIDC_TOKEN", "").strip()
    if pulled:
        return pulled
    if _TOKEN["value"] and time.time() < _TOKEN["expires"] - TOKEN_REFRESH_MARGIN:
        return _TOKEN["value"]
    oidc_url = os.environ.get("STUDIOSHARE_OIDC_URL", "").strip()
    if not oidc_url:
        return ""
    response = await client.post(oidc_url)
    response.raise_for_status()
    payload = response.json()
    token = str(payload.get("token") or "") if isinstance(payload, dict) else ""
    if token:
        _TOKEN.update(value=token, expires=_expires_at(payload.get("expiresAt")))
    return token


_SHARED: dict = {"client": None, "loop": None}


def shared_client() -> httpx.AsyncClient:
    """One pooled client per event loop, so AI calls reuse TLS connections to the provider."""
    loop = asyncio.get_running_loop()
    client = _SHARED["client"]
    if client is None or client.is_closed or _SHARED["loop"] is not loop:
        # Per-call deadlines come from asyncio.wait_for in _exchange_within.
        client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
        _SHARED.update(client=client, loop=loop)
    return client


async def close_shared_client() -> None:
    client = _SHARED["client"]
    _SHARED.update(client=None, loop=None)
    if client is not None and not client.is_closed:
        await client.aclose()


def parse_json_content(content: str) -> dict:
    text = _FENCE.sub("", (content or "").strip())
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no object")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("not object")
    return value


def _log(
    model: str, outcome: str, started: float, usage: dict | None = None, provider: str = "none"
) -> None:
    usage = usage or {}
    logger.info(
        "provider=%s model=%s prompt=%s latency_ms=%s outcome=%s prompt_tokens=%s completion_tokens=%s",
        provider,
        model,
        PROMPT_VERSION,
        int((time.perf_counter() - started) * 1000),
        outcome,
        int(usage.get("prompt_tokens") or 0),
        int(usage.get("completion_tokens") or 0),
    )


def _gateway_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _headers() -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key()}",
        "Content-Type": "application/json",
        "X-Title": "Resume Engine",
    }
    referer = os.environ.get("OPENROUTER_APP_URL", "").strip()
    if referer:
        headers["HTTP-Referer"] = referer
    return headers


def _retry_wait(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After", "1")
    try:
        return min(MAX_RETRY_WAIT, max(0.0, float(raw)))
    except ValueError:
        return 1.0


def _message_text(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content") if isinstance(message, dict) else ""
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
        return "".join(parts)
    return str(content or "")


@dataclass
class _Exchange:
    kind: str
    content: str = ""
    usage: dict | None = None
    served_model: str = ""
    wait: float = 1.0


async def _exchange(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    model: str,
    messages: list[dict],
    schema: dict,
    name: str,
    use_schema: bool,
) -> _Exchange:
    body: dict = {"model": model, "temperature": 0, "messages": messages}
    if use_schema:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": name, "strict": True, "schema": schema},
        }
    response = await client.post(url, headers=headers, json=body)
    if response.status_code == 401:
        return _Exchange("unauthorized")
    if response.status_code == 429:
        return _Exchange("rate_limited", wait=_retry_wait(response))
    if response.status_code in (400, 422):
        return _Exchange("schema_rejected")
    if response.status_code >= 400:
        return _Exchange("unavailable")
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return _Exchange("ok", content="", served_model=model)
    usage = payload.get("usage") if isinstance(payload, dict) else {}
    served = payload.get("model") if isinstance(payload, dict) else ""
    return _Exchange(
        "ok",
        content=_message_text(payload if isinstance(payload, dict) else {}),
        usage=usage if isinstance(usage, dict) else {},
        served_model=str(served or model),
    )


def _blocked_model(model: str) -> bool:
    name = (model or "").lower()
    return any(part in name for part in ("content-safety", "moderation", "guard"))


def _parsed(outcome: _Exchange) -> dict | None:
    if outcome.kind != "ok" or _blocked_model(outcome.served_model):
        return None
    try:
        return parse_json_content(outcome.content)
    except ValueError:
        return None


async def _exchange_within(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    model: str,
    messages: list[dict],
    schema: dict,
    name: str,
    use_schema: bool,
    timeout: float = TIMEOUT_SECONDS,
) -> _Exchange:
    try:
        return await asyncio.wait_for(
            _exchange(client, url, headers, model, messages, schema, name, use_schema),
            timeout=timeout,
        )
    except (asyncio.TimeoutError, httpx.TimeoutException):
        return _Exchange("unavailable")


class _Unauthorized(Exception):
    pass


async def _complete_with(
    client: httpx.AsyncClient,
    provider: str,
    url: str,
    headers: dict[str, str],
    model: str,
    messages: list[dict],
    schema: dict,
    name: str,
    started: float,
    timeout: float = TIMEOUT_SECONDS,
    text_fallback: bool = False,
) -> AiCompletion:
    """One model: a rate-limit retry, then a JSON repair. Raises AiCallError.

    With `text_fallback`, a model that answers in prose twice returns `{"_text": prose}`
    instead of failing, so a chat can still show the answer.
    """

    async def call(body: list[dict]) -> _Exchange:
        outcome = await _exchange_within(client, url, headers, model, body, schema, name, False, timeout)
        if outcome.kind == "unauthorized":
            raise _Unauthorized()
        return outcome

    outcome = await call(messages)
    if outcome.kind == "rate_limited":
        await asyncio.sleep(outcome.wait)
        outcome = await call(messages)
        if outcome.kind == "rate_limited":
            _log(model, "rate_limited", started, outcome.usage, provider)
            raise AiCallError("rate_limited")
    if outcome.kind == "unavailable":
        _log(model, "unavailable", started, outcome.usage, provider)
        raise AiCallError("unavailable")
    data = _parsed(outcome)
    if data is not None:
        served = outcome.served_model or model
        _log(served, "ok", started, outcome.usage, provider)
        return AiCompletion(data=data, model=served)

    first = outcome
    repair = [
        *messages,
        {
            "role": "user",
            "content": "Return one JSON object only, with no markdown.",
        },
    ]
    outcome = await call(repair)
    if outcome.kind == "rate_limited":
        _log(model, "rate_limited", started, outcome.usage, provider)
        raise AiCallError("rate_limited")
    data = _parsed(outcome)
    if data is None and text_fallback:
        prose = next(
            (item for item in (first, outcome) if item.kind == "ok" and not _blocked_model(item.served_model) and item.content.strip()),
            None,
        )
        if prose is not None:
            served = prose.served_model or model
            _log(served, "text", started, prose.usage, provider)
            return AiCompletion(data={"_text": prose.content.strip()}, model=served)
    if data is None:
        status = "unavailable" if outcome.kind == "unavailable" else "invalid"
        _log(outcome.served_model or model, status, started, outcome.usage, provider)
        raise AiCallError(status)
    served = outcome.served_model or model
    _log(served, "ok", started, outcome.usage, provider)
    return AiCompletion(data=data, model=served)


async def _provider_headers(provider: Provider, client: httpx.AsyncClient) -> dict[str, str] | None:
    if provider.name != "studioshare":
        return _headers()
    try:
        token = await gateway_token(client)
    except (httpx.HTTPError, ValueError):
        return None
    return _gateway_headers(token) if token else None


def _keep_status(current: str, new: str) -> str:
    """A later provider's `unavailable` must not hide an earlier model's real answer status."""
    return current if current in {"invalid", "rate_limited"} and new == "unavailable" else new


async def complete_json(
    messages: list[dict],
    schema: dict,
    name: str,
    client: httpx.AsyncClient | None = None,
    *,
    timeout: float = TIMEOUT_SECONDS,
    text_fallback: bool = False,
) -> AiCompletion:
    """Return one JSON object from the first provider and model that produce one."""
    started = time.perf_counter()
    chain = providers()
    if not chain:
        _log(openrouter_model(), "unavailable", started)
        raise AiCallError("unavailable")

    client = client or shared_client()
    status = "unavailable"
    for provider in chain:
        headers = await _provider_headers(provider, client)
        if headers is None:
            _log(provider.models[0], "no_token", started, provider=provider.name)
            status = _keep_status(status, "unavailable")
            continue
        for model in provider.models:
            try:
                return await _complete_with(
                    client, provider.name, provider.url, headers, model, messages, schema, name, started,
                    timeout, text_fallback,
                )
            except AiCallError as exc:
                status = _keep_status(status, exc.status)
            except _Unauthorized:
                if provider.name == "studioshare":
                    clear_gateway_token()
                _log(model, "unauthorized", started, provider=provider.name)
                status = _keep_status(status, "unavailable")
                break
            except httpx.HTTPError:
                _log(model, "unavailable", started, provider=provider.name)
                status = _keep_status(status, "unavailable")
    raise AiCallError(status)
