"""OpenRouter chat client for optional resume review."""

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass

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


def model_name() -> str:
    return os.environ.get("OPENROUTER_MODEL", "").strip() or DEFAULT_MODEL


def api_key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", "").strip()


def is_free_model(model: str) -> bool:
    return model == DEFAULT_MODEL or model.endswith(":free")


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


def _log(model: str, outcome: str, started: float, usage: dict | None = None) -> None:
    usage = usage or {}
    logger.info(
        "model=%s prompt=%s latency_ms=%s outcome=%s prompt_tokens=%s completion_tokens=%s",
        model,
        PROMPT_VERSION,
        int((time.perf_counter() - started) * 1000),
        outcome,
        int(usage.get("prompt_tokens") or 0),
        int(usage.get("completion_tokens") or 0),
    )


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
    response = await client.post(OPENROUTER_URL, headers=_headers(), json=body)
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
    model: str,
    messages: list[dict],
    schema: dict,
    name: str,
    use_schema: bool,
) -> _Exchange:
    try:
        return await asyncio.wait_for(
            _exchange(client, model, messages, schema, name, use_schema),
            timeout=TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, httpx.TimeoutException):
        return _Exchange("unavailable")


async def complete_json(
    messages: list[dict],
    schema: dict,
    name: str,
    client: httpx.AsyncClient | None = None,
) -> AiCompletion:
    """Call a free OpenRouter model and return one JSON object."""
    model = model_name()
    started = time.perf_counter()
    if not is_free_model(model) or not api_key():
        _log(model, "unavailable", started)
        raise AiCallError("unavailable")

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
    try:
        outcome = await _exchange_within(client, model, messages, schema, name, False)
        if outcome.kind == "rate_limited":
            await asyncio.sleep(outcome.wait)
            outcome = await _exchange_within(client, model, messages, schema, name, False)
            if outcome.kind == "rate_limited":
                _log(model, "rate_limited", started, outcome.usage)
                raise AiCallError("rate_limited")
        data = _parsed(outcome)
        if data is not None:
            served = outcome.served_model or model
            _log(served, "ok", started, outcome.usage)
            return AiCompletion(data=data, model=served)

        repair = [
            *messages,
            {
                "role": "user",
                "content": "Return one JSON object only, with no markdown.",
            },
        ]
        outcome = await _exchange_within(client, model, repair, schema, name, False)
        if outcome.kind == "rate_limited":
            _log(model, "rate_limited", started, outcome.usage)
            raise AiCallError("rate_limited")
        data = _parsed(outcome)
        if data is None:
            status = "unavailable" if outcome.kind == "unavailable" else "invalid"
            _log(outcome.served_model or model, status, started, outcome.usage)
            raise AiCallError(status)
        served = outcome.served_model or model
        _log(served, "ok", started, outcome.usage)
        return AiCompletion(data=data, model=served)
    except httpx.HTTPError:
        _log(model, "unavailable", started)
        raise AiCallError("unavailable")
    finally:
        if owns_client:
            await client.aclose()
