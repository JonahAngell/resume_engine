"""AI definition of one job keyword, read in the context of its posting. Nothing here saves.

Only the posting is sent, never the resume. The answer explains the term; it does not judge
whether the user has the experience.
"""

import hashlib
import json
import logging

from .ai_client import AiCallError, ai_available, complete_json, model_name
from .ai_review import redact_job

logger = logging.getLogger("resume_engine.ai")

DEFINE_PROMPT_VERSION = "1"
MAX_TEXT = 400
DETAILS = {
    "unavailable": "AI definitions are unavailable right now.",
    "rate_limited": "The free model is rate limited. Try again in a minute.",
    "invalid": "The model response could not be validated. Try again.",
}
_CACHE: dict[str, dict] = {}
_CACHE_MAX = 64

DEFINE_SYSTEM = """You explain one term from a job posting to a job seeker who may not know it.
Return one JSON object with keys definition and in_this_job.
definition: one or two plain-language sentences saying what the term means. No jargon left unexplained.
in_this_job: one sentence on what the term likely means for this role, based on the requirement and posting; "" if the posting adds nothing.
Do not judge whether the reader has this experience. Do not invent facts about the employer."""

DEFINE_SCHEMA = {
    "type": "object",
    "properties": {
        "definition": {"type": "string"},
        "in_this_job": {"type": "string"},
    },
    "required": ["definition"],
}


def _clip(value, limit: int = MAX_TEXT) -> str:
    return " ".join(str(value or "").split())[:limit]


def _result(status: str, keyword: str, definition: str = "", in_this_job: str = "", model: str = "") -> dict:
    return {
        "status": status,
        "detail": DETAILS.get(status, ""),
        "keyword": keyword,
        "definition": definition,
        "in_this_job": in_this_job,
        "model": model,
    }


async def define_keyword(description: str, keyword: str, requirement: str, complete=None) -> dict:
    keyword = _clip(keyword, 200)
    model = model_name()
    if complete is None:
        complete = complete_json
        if not ai_available():
            return _result("unavailable", keyword)
    request = {
        "term": keyword,
        "requirement": _clip(requirement, 2000),
        "posting": redact_job(description or "")[:8000],
    }
    key = hashlib.sha256(
        json.dumps([request, DEFINE_PROMPT_VERSION, model]).encode("utf-8")
    ).hexdigest()
    cached = _CACHE.get(key)
    if cached is not None:
        return dict(cached)

    messages = [
        {"role": "system", "content": DEFINE_SYSTEM},
        {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
    ]
    try:
        completion = await complete(messages, DEFINE_SCHEMA, "keyword_define")
    except AiCallError as exc:
        logger.info("keyword_define prompt=%s outcome=%s", DEFINE_PROMPT_VERSION, exc.status)
        return _result(exc.status, keyword)
    data = getattr(completion, "data", None)
    definition = _clip(data.get("definition")) if isinstance(data, dict) else ""
    if not definition:
        return _result("invalid", keyword)
    served = getattr(completion, "model", "") or model
    payload = _result("ok", keyword, definition, _clip(data.get("in_this_job")), served)
    logger.info("keyword_define prompt=%s outcome=ok model=%s", DEFINE_PROMPT_VERSION, served)
    _CACHE[key] = payload
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    return dict(payload)


def clear_cache() -> None:
    _CACHE.clear()
