"""Optional AI rewrites of one placed bullet for one job. Nothing here saves.

The model may reshape wording toward the job, but a draft that adds a number, tool, proper
noun, or guarded keyword the original bullet does not show is dropped. In keyword mode every
draft must also use the job keyword, and the model may say the keyword does not fit.
"""

import hashlib
import json
import logging
import re

from .ai_client import AiCallError, ai_available, complete_json, model_name
from .ai_review import redact_job, scrub
from .job_match import extract_keywords
from .related_skills import DICTIONARY, category_for_term

logger = logging.getLogger("resume_engine.ai")

VARIANT_PROMPT_VERSION = "3"
GOALS = {
    "concise": "Make it shorter and tighter.",
    "impact": "Lead with the outcome the bullet already states.",
    "align": "Use the job's wording for the requirement where the bullet already supports it.",
    "one_line": (
        "Fit on one resume line: at most max_chars characters. Cut filler words and soft phrasing; "
        "keep the action, the outcome, and every number that matters."
    ),
}
ONE_LINE_CHARS = 95
GUARDED_CATEGORIES = {"tool", "credential", "degree", "experience_duration"}
MAX_DRAFTS = 5
MAX_BODY = 500
MAX_NAME = 60
MAX_RATIONALE = 240
LENGTH_RATIO = 1.6
LENGTH_SLACK = 60
DETAILS = {
    "unavailable": "AI suggestions are unavailable. The bullet is unchanged.",
    "rate_limited": "The free model is rate limited. The bullet is unchanged.",
    "invalid": "The model response could not be validated. The bullet is unchanged.",
}
MAX_REASON = 240
_CACHE: dict[str, dict] = {}
_CACHE_MAX = 32
# placement id -> {folded body: (model, job id)} for drafts this process handed out.
_ISSUED: dict[str, dict[str, tuple[str, str]]] = {}
_ISSUED_MAX = 64

VARIANT_SYSTEM = """You rewrite one resume bullet for a specific job posting.
Return one JSON object with keys drafts, fits, and reason.
drafts: a list of 3 to 5 items, each with name, body, and rationale.
name: 2 to 4 words describing the angle, for example "Outcome first".
body: the rewritten bullet, one sentence, no leading bullet character.
rationale: one short sentence on why this wording suits the requirement.
fits: false only when keyword_rule asks for the keyword and it cannot honestly describe this bullet's work; then drafts is empty.
reason: when fits is false, one short sentence why; else "".
Rules:
- Every fact must come from the original bullet. Do not add numbers, tools, products, employers, people, places, or certifications it does not state.
- The posting may guide emphasis and word choice only.
- Each draft must take a different angle.
- Follow keyword_rule.
- Do not return the original wording unchanged."""

VARIANT_SCHEMA = {
    "type": "object",
    "properties": {
        "drafts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "body": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["name", "body", "rationale"],
            },
        },
        "fits": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["drafts"],
}

_NUMBER = re.compile(r"\$?\d[\d,.]*%?|\b\d+(?:st|nd|rd|th)\b", re.IGNORECASE)
_SPELLED = {
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "hundred", "hundreds",
    "thousand", "thousands", "million", "millions", "billion", "dozen", "dozens",
    "double", "doubled", "triple", "tripled", "half", "percent",
}
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9&+#./-]*")
_CAPITALISED_OK = {"i", "ai"}


def _fold(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _numbers(text: str) -> set[str]:
    found = {match.group(0).strip("$%.,").replace(",", "") for match in _NUMBER.finditer(text or "")}
    words = {word.casefold() for word in re.findall(r"[A-Za-z]+", text or "")}
    return {item for item in found if item} | (words & _SPELLED)


def _proper_nouns(text: str) -> set[str]:
    """Capitalised words that do not start a sentence, plus acronyms anywhere."""
    found = set()
    sentence_start = True
    for match in _WORD.finditer(text or ""):
        word = match.group(0).rstrip(".,;:")
        before = (text or "")[: match.start()].rstrip()
        sentence_start = not before or before[-1] in ".!?:;—-("
        acronym = len(word) >= 2 and sum(char.isupper() for char in word) >= 2
        if acronym or (word[:1].isupper() and not sentence_start):
            if word.casefold() not in _CAPITALISED_OK:
                found.add(word.casefold())
    return found


def _contains(text: str, term: str) -> bool:
    if not term.strip():
        return False
    pattern = r"(?<!\w)" + re.escape(term.strip()) + r"(?!\w)"
    return re.search(pattern, text or "", re.IGNORECASE) is not None


def _keyword_allowed(keyword: str, category: str) -> bool:
    return bool(keyword) and category not in GUARDED_CATEGORIES


def has_keyword(text: str, keyword: str) -> bool:
    """The keyword, or a dictionary form of it ("A/B tests" for "A/B Testing"), appears in text."""
    if not (keyword or "").strip():
        return False
    return _contains(text, keyword) or DICTIONARY.mentions(keyword, text or "")


def drop_reason(
    body: str,
    original: str,
    keyword: str,
    category: str,
    job_terms: list[str],
    *,
    require_keyword: bool = False,
    fresh: bool = False,
) -> str:
    """Return why a draft is unsafe, or "" when it may be shown.

    `fresh` is for a new bullet: `original` is then the entry's text, the only fact source, so
    the length ratio and unchanged checks do not apply.
    """
    text = " ".join((body or "").split())
    if not text:
        return "empty"
    if len(text) > MAX_BODY:
        return "length"
    if not fresh and len(text) > max(len(original) * LENGTH_RATIO, len(original) + LENGTH_SLACK):
        return "length"
    if not fresh and _fold(text) == _fold(original):
        return "unchanged"
    if require_keyword and _keyword_allowed(keyword, category) and not has_keyword(text, keyword):
        return "missing_keyword"
    if _numbers(text) - _numbers(original):
        return "number"
    allowed = _keyword_allowed(keyword, category)
    if keyword and not allowed and _contains(text, keyword) and not _contains(original, keyword):
        return "guarded_keyword"
    for term in DICTIONARY.match_terms(text):
        if DICTIONARY.mentions(term, original) or _contains(original, term):
            continue
        # The allowed keyword, or a word of it ("forecasting" in "Financial Forecasting"), may shape wording.
        part_of_keyword = _contains(keyword, term) or DICTIONARY.canonical(term) == DICTIONARY.canonical(keyword)
        if allowed and part_of_keyword and category_for_term(term) != "tool":
            continue
        return "tool"
    for term in job_terms:
        if not _contains(text, term) or _contains(original, term):
            continue
        if allowed and _fold(term) == _fold(keyword) and category_for_term(term) != "tool":
            continue
        return "tool"
    original_words = {word.casefold().rstrip(".,;:") for word in _WORD.findall(original or "")}
    keyword_words = {word.casefold() for word in _WORD.findall(keyword or "")} if allowed else set()
    if _proper_nouns(text) - original_words - keyword_words:
        return "proper_noun"
    return ""


def filter_drafts(
    data: dict,
    original: str,
    keyword: str,
    category: str,
    job_terms: list[str],
    require_keyword: bool = False,
    max_chars: int | None = None,
) -> tuple[list[dict], int]:
    drafts = data.get("drafts") if isinstance(data, dict) else None
    if not isinstance(drafts, list):
        return [], 0
    kept: list[dict] = []
    seen = {_fold(original)}
    dropped = 0
    for index, item in enumerate(drafts):
        if not isinstance(item, dict):
            dropped += 1
            continue
        body = " ".join(str(item.get("body") or "").split()).lstrip("•-* ").strip()
        too_long = max_chars is not None and len(body) > max_chars
        if too_long or _fold(body) in seen or drop_reason(body, original, keyword, category, job_terms, require_keyword=require_keyword):
            dropped += 1
            continue
        seen.add(_fold(body))
        name = " ".join(str(item.get("name") or "").split())[:MAX_NAME] or f"AI draft {index + 1}"
        rationale = " ".join(str(item.get("rationale") or "").split())[:MAX_RATIONALE]
        kept.append({"name": name, "body": body, "rationale": rationale})
        if len(kept) >= MAX_DRAFTS:
            break
    return kept, dropped


def _cache_key(original, job, requirement, keyword, category, goal, model, incorporate=False, max_chars=None) -> str:
    raw = json.dumps(
        [original, job, requirement, keyword, category, goal, VARIANT_PROMPT_VERSION, model, incorporate, max_chars]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def job_tool_terms(description: str) -> list[str]:
    """Job keywords a draft may not claim: dictionary tools and capitalised unknown terms."""
    terms = []
    for item in extract_keywords(description or ""):
        keyword = item["keyword"]
        category = category_for_term(keyword)
        if category == "tool" or (category is None and any(char.isupper() for char in keyword)):
            terms.append(keyword)
    return terms


def remember_issued(placement_id: str, drafts: list[dict], model: str, job_id: str) -> None:
    if not placement_id:
        return
    issued = _ISSUED.pop(placement_id, {})
    for draft in drafts:
        issued[_fold(draft["body"])] = (model, job_id)
    _ISSUED[placement_id] = issued
    while len(_ISSUED) > _ISSUED_MAX:
        _ISSUED.pop(next(iter(_ISSUED)))


def issued_draft(placement_id: str, body: str, job_id: str) -> str | None:
    """The model that wrote this exact draft for this placement and job, if this process issued it."""
    entry = (_ISSUED.get(str(placement_id)) or {}).get(_fold(body))
    if entry and entry[1] == str(job_id):
        return entry[0]
    return None


def _result(status: str, model: str = "", drafts=None, dropped: int = 0, fits: bool = True, reason: str = "") -> dict:
    return {
        "status": status,
        "detail": DETAILS.get(status, ""),
        "model": model,
        "drafts": drafts or [],
        "dropped": dropped,
        "fits": fits,
        "reason": reason,
    }


async def suggest_variants(
    original: str,
    job_text: str,
    requirement: str,
    keyword: str,
    category: str = "",
    goal: str | None = None,
    job_terms: list[str] | None = None,
    placement_id: str = "",
    job_id: str = "",
    incorporate_keyword: bool = False,
    max_chars: int | None = None,
    complete=None,
) -> dict:
    model = model_name()
    if complete is None:
        complete = complete_json
        if not ai_available():
            return _result("unavailable")
    bullet = scrub(original or "", [])
    job = redact_job(job_text or "")[:12000]
    category = category or category_for_term(keyword) or ""
    goal = goal if goal in GOALS else None
    # Only the one-line goal has a hard length budget.
    max_chars = (max_chars or ONE_LINE_CHARS) if goal == "one_line" else None
    terms = [term for term in (job_terms or []) if term and term.strip()]
    # Keyword mode only applies to keywords drafts may add; guarded ones keep the old rule.
    require = bool(incorporate_keyword) and _keyword_allowed(keyword, category)
    key = _cache_key(bullet, job, requirement, keyword, category, goal, model, require, max_chars)
    cached = _CACHE.get(key)
    if cached is not None:
        remember_issued(placement_id, cached["drafts"], cached["model"], job_id)
        return json.loads(json.dumps(cached))

    guard = (
        f'Every draft must use the phrase "{keyword}" (or a close form of it), worked in where it '
        "describes the work this bullet states. Add no other facts. If it cannot honestly describe "
        "this work, return no drafts, set fits to false, and give a short reason."
        if require
        else f'Do not add "{keyword}" unless the original bullet already says it.'
        if keyword and not _keyword_allowed(keyword, category)
        else f'You may use the words "{keyword}" only if the bullet already shows that work.'
        if keyword
        else ""
    )
    request = {
        "original_bullet": bullet,
        "requirement": requirement,
        "keyword": keyword,
        "keyword_rule": guard,
        "goal": GOALS.get(goal or "", "Offer a mix of angles."),
        "posting": job or "No job chosen. Keep the bullet's own emphasis.",
    }
    if max_chars:
        request["max_chars"] = max_chars
    messages = [
        {"role": "system", "content": VARIANT_SYSTEM},
        {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
    ]
    try:
        completion = await complete(messages, VARIANT_SCHEMA, "bullet_variants")
    except AiCallError as exc:
        logger.info("bullet_variants prompt=%s outcome=%s", VARIANT_PROMPT_VERSION, exc.status)
        return _result(exc.status)
    data = getattr(completion, "data", None)
    if not isinstance(data, dict):
        return _result("invalid")
    served = getattr(completion, "model", "") or model
    drafts, dropped = filter_drafts(data, bullet, keyword, category, terms, require, max_chars)
    fits = data.get("fits") is not False or bool(drafts)
    reason = "" if fits else " ".join(str(data.get("reason") or "").split())[:MAX_REASON]
    logger.info(
        "bullet_variants prompt=%s outcome=ok model=%s kept=%s dropped=%s",
        VARIANT_PROMPT_VERSION,
        served,
        len(drafts),
        dropped,
    )
    payload = _result("ok", served, drafts, dropped, fits, reason)
    _CACHE[key] = payload
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    remember_issued(placement_id, drafts, served, job_id)
    return json.loads(json.dumps(payload))


def clear_cache() -> None:
    _CACHE.clear()
    _ISSUED.clear()
