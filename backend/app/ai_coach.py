"""AI coach: one review of the whole resume against the whole job, as actionable cards.

The model proposes; the server keeps only what it can check. Rewrites and summary edits pass
the same guard as single-bullet drafts. Skill gaps carry no AI text and go to Add to Skills.
Nothing here saves; accepting a card uses the existing accept endpoints.
"""

import hashlib
import json
import logging
import re

from .ai_client import AiCallError, ai_available, complete_json, model_name
from .ai_review import redact_job, scrub
from .ai_variants import drop_reason, job_tool_terms, remember_issued
from .job_match import is_skill_keyword, match_qualifications

logger = logging.getLogger("resume_engine.ai")

COACH_PROMPT_VERSION = "1"
MAX_SUGGESTIONS = 12
MAX_EQUIVALENTS = 8
MAX_BULLETS = 40
MAX_RATIONALE = 300
DETAILS = {
    "unavailable": "AI review is unavailable. Your resume is unchanged.",
    "rate_limited": "The free model is rate limited. Your resume is unchanged.",
    "invalid": "The model response could not be validated. Your resume is unchanged.",
}
GROUP_ORDER = {"required": 0, "preferred": 1, "responsibilities": 2}
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_CACHE: dict[str, dict] = {}
_CACHE_MAX = 16

COACH_SYSTEM = """You are a resume coach. Compare one resume with one job posting and suggest concrete edits.
Return one JSON object with keys suggestions and equivalents.
suggestions: up to 12 items, most important first. Each item has:
  kind: "rewrite" (reword one numbered bullet), "summary" (reword the summary), or "add_skill" (a tool or skill the job wants that belongs in the Skills section);
  bullet: the bullet number for "rewrite", else null;
  requirement: the job requirement this addresses, copied exactly from the requirements list;
  keyword: the requirement keyword it targets, or "";
  proposed: the full new wording for "rewrite" and "summary", else "";
  rationale: one short sentence;
  priority: "high", "medium" or "low".
equivalents: requirements the resume already meets in other words. Each item has requirement (copied exactly), bullet (number), and rationale.
Rules:
- Every fact in proposed wording must already be in the bullet or summary you rewrite. Never add numbers, tools, products, employers, people, places or certifications.
- The posting may guide emphasis and word choice only.
- Prefer required requirements over preferred ones.
- Do not suggest a rewrite that only changes punctuation."""

COACH_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {"type": "array", "items": {"type": "object"}},
        "equivalents": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["suggestions", "equivalents"],
}


def _fold(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _clip(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _rows(match: dict) -> list[dict]:
    rows = []
    for group in ("required", "preferred", "responsibilities"):
        for row in match.get(group) or []:
            if isinstance(row, dict):
                rows.append({**row, "group": group})
    return rows


def _requirement_index(rows: list[dict]) -> dict[str, dict]:
    return {_fold(row["text"]): row for row in rows}


def _keyword_for(row: dict, wanted: str) -> str:
    keywords = row.get("keywords") or []
    for item in keywords:
        if wanted and _fold(item.get("keyword")) == _fold(wanted):
            return item.get("keyword") or ""
    for item in keywords:
        if not item.get("found") and not item.get("skipped"):
            return item.get("keyword") or ""
    return keywords[0].get("keyword", "") if keywords else ""


def _keyword_found(row: dict, keyword: str) -> bool:
    return any(_fold(item.get("keyword")) == _fold(keyword) and item.get("found") for item in row.get("keywords") or [])


def _keyword_skipped(row: dict, keyword: str) -> bool:
    """The user said they lack this keyword, so the coach never suggests it."""
    return any(_fold(item.get("keyword")) == _fold(keyword) and item.get("skipped") for item in row.get("keywords") or [])


def _card_id(*parts) -> str:
    return hashlib.sha1(json.dumps(parts).encode("utf-8")).hexdigest()[:12]


def filter_coach(data: dict, bullets: list[dict], summary: str, rows: list[dict], job_terms: list[str]) -> dict:
    """Keep only suggestions the server can check. `bullets` are numbered from 1."""
    by_requirement = _requirement_index(rows)
    suggestions: list[dict] = []
    seen: set[tuple] = set()
    dropped = 0
    for item in data.get("suggestions") or []:
        if not isinstance(item, dict):
            dropped += 1
            continue
        kind = item.get("kind")
        row = by_requirement.get(_fold(item.get("requirement")))
        if kind not in {"rewrite", "summary", "add_skill"} or not row:
            dropped += 1
            continue
        category = row.get("category") or row.get("kind") or ""
        keyword = _keyword_for(row, _clip(item.get("keyword"), 120))
        if keyword and _keyword_skipped(row, keyword):
            dropped += 1
            continue
        priority = item.get("priority") if item.get("priority") in PRIORITY_ORDER else "medium"
        card = {
            "kind": kind,
            "requirement": row["text"],
            "group": row["group"],
            "category": category,
            "keyword": keyword,
            "placement_id": "",
            "original": "",
            "proposed": "",
            "rationale": _clip(item.get("rationale"), MAX_RATIONALE),
            "priority": priority,
        }
        if kind == "add_skill":
            if row.get("matched") or not keyword or _keyword_found(row, keyword) or not is_skill_keyword(keyword, category):
                dropped += 1
                continue
            key = (kind, _fold(keyword))
        else:
            proposed = _clip(item.get("proposed"), 600).lstrip("•-* ")
            if kind == "rewrite":
                index = item.get("bullet")
                if not isinstance(index, int) or not 1 <= index <= len(bullets):
                    dropped += 1
                    continue
                bullet = bullets[index - 1]
                original = bullet["text"]
                card["placement_id"] = bullet["placement_id"]
            else:
                original = summary
                if not original.strip():
                    dropped += 1
                    continue
            if drop_reason(proposed, original, keyword, category, job_terms):
                dropped += 1
                continue
            card["original"], card["proposed"] = original, proposed
            key = (kind, card["placement_id"], _fold(proposed))
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        card["id"] = _card_id(kind, card["requirement"], card["placement_id"], card["keyword"], card["proposed"])
        suggestions.append(card)
    suggestions.sort(key=lambda card: (GROUP_ORDER.get(card["group"], 3), PRIORITY_ORDER[card["priority"]]))
    suggestions = suggestions[:MAX_SUGGESTIONS]

    equivalents: list[dict] = []
    for item in data.get("equivalents") or []:
        row = by_requirement.get(_fold(item.get("requirement"))) if isinstance(item, dict) else None
        index = item.get("bullet") if isinstance(item, dict) else None
        if not row or row.get("matched") or not isinstance(index, int) or not 1 <= index <= len(bullets):
            dropped += 1
            continue
        if any(entry["requirement"] == row["text"] for entry in equivalents):
            continue
        bullet = bullets[index - 1]
        equivalents.append(
            {
                "id": _card_id("equivalent", row["text"], bullet["placement_id"]),
                "requirement": row["text"],
                "group": row["group"],
                "placement_id": bullet["placement_id"],
                "bullet": bullet["text"],
                "rationale": _clip(item.get("rationale"), MAX_RATIONALE),
            }
        )
        if len(equivalents) >= MAX_EQUIVALENTS:
            break
    return {"suggestions": suggestions, "equivalents": equivalents, "dropped": dropped}


def _result(status: str, revision: int, model: str = "", part: dict | None = None) -> dict:
    part = part or {}
    return {
        "status": status,
        "detail": DETAILS.get(status, ""),
        "model": model,
        "revision": revision,
        "suggestions": part.get("suggestions") or [],
        "equivalents": part.get("equivalents") or [],
        "dropped": int(part.get("dropped") or 0),
    }


async def coach_resume(
    description: str,
    resume: dict,
    placed: list[dict],
    review: dict | None,
    revision: int,
    job_id: str = "",
    complete=None,
) -> dict:
    model = model_name()
    if complete is None:
        complete = complete_json
        if not ai_available():
            return _result("unavailable", revision)
    match = match_qualifications(description or "", resume or {}, placed, review or {})
    rows = _rows(match)
    job = redact_job(description or "")[:12000]
    bullets = [
        {"placement_id": str(item.get("placement_id") or ""), "section": item.get("section") or "", "text": scrub(item.get("wording") or "", [])}
        for item in placed or []
        if item.get("placement_id") and (item.get("wording") or "").strip()
    ][:MAX_BULLETS]
    summary = scrub((resume or {}).get("summary") or "", [])
    job_terms = job_tool_terms(description or "")
    requirements = [
        {"text": row["text"], "group": row["group"], "matched": bool(row.get("matched")),
         "keywords": [item.get("keyword") for item in row.get("keywords") or [] if not item.get("skipped")]}
        for row in rows
    ][:60]
    key = hashlib.sha256(
        json.dumps([job, bullets, summary, requirements, revision, COACH_PROMPT_VERSION, model]).encode("utf-8")
    ).hexdigest()
    cached = _CACHE.get(key)
    if cached is not None:
        _remember(cached, job_id)
        return json.loads(json.dumps(cached))

    request = {
        "posting": job,
        "requirements": requirements,
        "summary": summary,
        "bullets": [{"number": index + 1, "section": item["section"], "text": item["text"]} for index, item in enumerate(bullets)],
    }
    messages = [
        {"role": "system", "content": COACH_SYSTEM},
        {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
    ]
    try:
        completion = await complete(messages, COACH_SCHEMA, "resume_coach")
    except AiCallError as exc:
        logger.info("resume_coach prompt=%s outcome=%s", COACH_PROMPT_VERSION, exc.status)
        return _result(exc.status, revision)
    data = getattr(completion, "data", None)
    if not isinstance(data, dict):
        return _result("invalid", revision)
    served = getattr(completion, "model", "") or model
    part = filter_coach(data, bullets, summary, rows, job_terms)
    logger.info(
        "resume_coach prompt=%s outcome=ok model=%s kept=%s equivalents=%s dropped=%s",
        COACH_PROMPT_VERSION,
        served,
        len(part["suggestions"]),
        len(part["equivalents"]),
        part["dropped"],
    )
    payload = _result("ok", revision, served, part)
    _CACHE[key] = payload
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _remember(payload, job_id)
    return json.loads(json.dumps(payload))


def _remember(payload: dict, job_id: str) -> None:
    # Unchanged accepted rewrites then count as AI-written, like single-bullet drafts.
    for card in payload["suggestions"]:
        if card["kind"] == "rewrite" and card["placement_id"]:
            remember_issued(card["placement_id"], [{"body": card["proposed"]}], payload["model"], job_id)


def clear_cache() -> None:
    _CACHE.clear()
