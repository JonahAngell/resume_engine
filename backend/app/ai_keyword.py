"""AI help for one job keyword across the whole resume. Nothing here saves.

The model may reword placed bullets so they use the keyword, and draft new bullets for a role or
project. Revisions pass the single-bullet guard against their own bullet. A new bullet has no
original, so its fact source is its entry: the title, organization, and that entry's bullets.
Missing numbers become [placeholders] the user must fill in before saving.
"""

import hashlib
import json
import logging
import re

from .ai_client import AiCallError, ai_available, complete_json, model_name
from .ai_review import redact_job, scrub
from .ai_variants import _fold, _keyword_allowed, drop_reason, job_tool_terms, remember_issued
from .job_match import _placement_options

logger = logging.getLogger("resume_engine.ai")

KEYWORD_PROMPT_VERSION = "1"
MAX_REVISIONS = 3
MAX_NEW = 2
MAX_BULLETS = 40
MAX_RATIONALE = 240
MAX_REASON = 240
ENTRY_SECTIONS = {"work_experience": "Work Experience", "projects": "Projects", "leadership": "Leadership"}
PLACEHOLDER = re.compile(r"\[[^\[\]\n]{1,30}\]")
DETAILS = {
    "unavailable": "AI suggestions are unavailable. Your resume is unchanged.",
    "rate_limited": "The free model is rate limited. Your resume is unchanged.",
    "invalid": "The model response could not be validated. Your resume is unchanged.",
}
_CACHE: dict[str, dict] = {}
_CACHE_MAX = 16

KEYWORD_SYSTEM = """You help a job seeker work one keyword from a job posting into their resume.
Return one JSON object with keys revisions, new_bullets, and no_fit_reason.
revisions: up to 3 items, each with bullet (a bullet number), body, and rationale. Rewrite that bullet so it uses the keyword. Only pick bullets whose work the keyword honestly describes. Bullets marked likely_fit are good candidates, but you may pick any.
new_bullets: up to 2 items, each with entry (an entry number), body, and rationale. A new bullet for that role or project, about work it plausibly involved, using the keyword.
no_fit_reason: when nothing fits, one short sentence why; else "".
Rules:
- Every body must contain the keyword phrase.
- A revision keeps the facts of its bullet and adds none: no new numbers, tools, products, employers, people, places, or certifications.
- A new bullet may only use facts from its entry: the title, organization, and its bullets. Where a number would help but the entry states none, write a placeholder in square brackets such as [X%] or [N teams].
- One sentence each, no leading bullet character.
- The posting may guide emphasis and word choice only.
- rationale: one short sentence."""

KEYWORD_SCHEMA = {
    "type": "object",
    "properties": {
        "revisions": {"type": "array", "items": {"type": "object"}},
        "new_bullets": {"type": "array", "items": {"type": "object"}},
        "no_fit_reason": {"type": "string"},
    },
    "required": ["revisions", "new_bullets"],
}


def _clip(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _body(value) -> str:
    return _clip(value, 600).lstrip("•-* ").strip()


def _card_id(*parts) -> str:
    return hashlib.sha1(json.dumps(parts).encode("utf-8")).hexdigest()[:12]


def _entry_label(section: str, entry: dict) -> str:
    if section == "projects":
        parts = [entry.get("name"), entry.get("subtitle")]
    else:
        parts = [entry.get("title"), entry.get("organization")]
    return ", ".join(_clip(part, 120) for part in parts if _clip(part, 120))


def resume_entries(resume: dict, placed: list[dict]) -> tuple[list[dict], list[dict]]:
    """Numbered entries (roles and projects) and placed bullets, both in resume order.

    Each bullet carries the number of its entry, or None when it sits under something else.
    """
    entries: list[dict] = []
    by_parent: dict[str, int] = {}
    for section in ENTRY_SECTIONS:
        for entry in (resume or {}).get(section) or []:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            label = _entry_label(section, entry)
            if not label:
                continue
            parent_id = str(entry["id"])
            by_parent[parent_id] = len(entries) + 1
            entries.append(
                {
                    "parent_id": parent_id,
                    "section": section,
                    "entry": label,
                    "facts": " ".join(
                        _clip(entry.get(key), 160) for key in ("title", "organization", "name", "subtitle", "location")
                    ),
                    "bullets": [],
                }
            )
    bullets: list[dict] = []
    for item in placed or []:
        text = scrub(item.get("wording") or "", [])
        if not item.get("placement_id") or not text.strip():
            continue
        number = by_parent.get(str(item.get("parent_id") or ""))
        bullet = {
            "placement_id": str(item["placement_id"]),
            "section": item.get("section") or "",
            "entry": entries[number - 1]["entry"] if number else "",
            "entry_number": number,
            "text": text,
        }
        bullets.append(bullet)
        if number:
            entries[number - 1]["bullets"].append(text)
    return entries, bullets[:MAX_BULLETS]


def entry_facts(entry: dict) -> str:
    return " ".join([entry["facts"], *entry["bullets"]]).strip()


def without_placeholders(text: str) -> str:
    return " ".join(PLACEHOLDER.sub(" ", text or "").split())


def filter_keyword(
    data: dict, entries: list[dict], bullets: list[dict], keyword: str, category: str, job_terms: list[str]
) -> dict:
    """Keep only drafts the server can check. Entries and bullets are numbered from 1."""
    revisions: list[dict] = []
    new_bullets: list[dict] = []
    dropped = 0
    used: set[str] = set()
    for item in data.get("revisions") or []:
        index = item.get("bullet") if isinstance(item, dict) else None
        if not isinstance(index, int) or not 1 <= index <= len(bullets) or len(revisions) >= MAX_REVISIONS:
            dropped += 1
            continue
        bullet = bullets[index - 1]
        body = _body(item.get("body"))
        if (
            bullet["placement_id"] in used
            or PLACEHOLDER.search(body)
            or drop_reason(body, bullet["text"], keyword, category, job_terms, require_keyword=True)
        ):
            dropped += 1
            continue
        used.add(bullet["placement_id"])
        revisions.append(
            {
                "id": _card_id("revision", bullet["placement_id"], body),
                "placement_id": bullet["placement_id"],
                "section": bullet["section"],
                "entry": bullet["entry"],
                "original": bullet["text"],
                "body": body,
                "rationale": _clip(item.get("rationale"), MAX_RATIONALE),
            }
        )
    seen = {_fold(bullet["text"]) for bullet in bullets}
    for item in data.get("new_bullets") or []:
        index = item.get("entry") if isinstance(item, dict) else None
        if not isinstance(index, int) or not 1 <= index <= len(entries) or len(new_bullets) >= MAX_NEW:
            dropped += 1
            continue
        entry = entries[index - 1]
        body = _body(item.get("body"))
        checked = without_placeholders(body)
        if (
            not checked
            or _fold(body) in seen
            or drop_reason(checked, entry_facts(entry), keyword, category, job_terms, require_keyword=True, fresh=True)
        ):
            dropped += 1
            continue
        seen.add(_fold(body))
        new_bullets.append(
            {
                "id": _card_id("new", entry["parent_id"], body),
                "parent_id": entry["parent_id"],
                "section": entry["section"],
                "entry": entry["entry"],
                "body": body,
                "rationale": _clip(item.get("rationale"), MAX_RATIONALE),
                "placeholders": bool(PLACEHOLDER.search(body)),
            }
        )
    return {"revisions": revisions, "new_bullets": new_bullets, "dropped": dropped}


def new_bullet_key(parent_id) -> str:
    """The issued-draft key for new bullets under one entry."""
    return f"new:{parent_id}"


def _public_entries(entries: list[dict]) -> list[dict]:
    return [{"parent_id": item["parent_id"], "section": item["section"], "entry": item["entry"]} for item in entries]


def _result(status: str, revision: int, keyword: str, category: str, entries: list[dict], model: str = "", part=None) -> dict:
    part = part or {}
    return {
        "status": status,
        "detail": DETAILS.get(status, ""),
        "model": model,
        "revision": revision,
        "keyword": keyword,
        "category": category,
        "allowed": _keyword_allowed(keyword, category),
        "revisions": part.get("revisions") or [],
        "new_bullets": part.get("new_bullets") or [],
        "entries": _public_entries(entries),
        "no_fit_reason": part.get("no_fit_reason") or "",
        "dropped": int(part.get("dropped") or 0),
    }


async def assist_keyword(
    description: str,
    resume: dict,
    placed: list[dict],
    keyword: str,
    requirement: str,
    category: str,
    revision: int,
    job_id: str = "",
    complete=None,
) -> dict:
    keyword = _clip(keyword, 200)
    entries, bullets = resume_entries(resume, placed)
    if not _keyword_allowed(keyword, category):
        # Tools, credentials, degrees and durations are never written in by the model.
        return _result("ok", revision, keyword, category, entries)
    model = model_name()
    if complete is None:
        complete = complete_json
        if not ai_available():
            return _result("unavailable", revision, keyword, category, entries)
    job = redact_job(description or "")[:12000]
    job_terms = job_tool_terms(description or "")
    likely = {
        option.get("placement_id")
        for option in _placement_options(keyword, requirement or keyword, placed or [], [])
        if option.get("placement_id")
    }
    request = {
        "keyword": keyword,
        "requirement": requirement,
        "posting": job,
        "entries": [
            {"number": index + 1, "section": ENTRY_SECTIONS[item["section"]], "entry": item["entry"]}
            for index, item in enumerate(entries)
        ],
        "bullets": [
            {
                "number": index + 1,
                "entry": item["entry_number"],
                "section": item["section"],
                "text": item["text"],
                **({"likely_fit": True} if item["placement_id"] in likely else {}),
            }
            for index, item in enumerate(bullets)
        ],
    }
    key = hashlib.sha256(
        json.dumps([request, category, revision, KEYWORD_PROMPT_VERSION, model]).encode("utf-8")
    ).hexdigest()
    cached = _CACHE.get(key)
    if cached is not None:
        _remember(cached, job_id)
        return json.loads(json.dumps(cached))

    messages = [
        {"role": "system", "content": KEYWORD_SYSTEM},
        {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
    ]
    try:
        completion = await complete(messages, KEYWORD_SCHEMA, "keyword_assist")
    except AiCallError as exc:
        logger.info("keyword_assist prompt=%s outcome=%s", KEYWORD_PROMPT_VERSION, exc.status)
        return _result(exc.status, revision, keyword, category, entries)
    data = getattr(completion, "data", None)
    if not isinstance(data, dict):
        return _result("invalid", revision, keyword, category, entries)
    served = getattr(completion, "model", "") or model
    part = filter_keyword(data, entries, bullets, keyword, category, job_terms)
    if not part["revisions"] and not part["new_bullets"]:
        part["no_fit_reason"] = _clip(data.get("no_fit_reason"), MAX_REASON)
    logger.info(
        "keyword_assist prompt=%s outcome=ok model=%s revisions=%s new=%s dropped=%s",
        KEYWORD_PROMPT_VERSION,
        served,
        len(part["revisions"]),
        len(part["new_bullets"]),
        part["dropped"],
    )
    payload = _result("ok", revision, keyword, category, entries, served, part)
    _CACHE[key] = payload
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _remember(payload, job_id)
    return json.loads(json.dumps(payload))


def _remember(payload: dict, job_id: str) -> None:
    # Unchanged accepted drafts then count as AI-written, like single-bullet drafts.
    for card in payload["revisions"]:
        remember_issued(card["placement_id"], [card], payload["model"], job_id)
    for card in payload["new_bullets"]:
        remember_issued(new_bullet_key(card["parent_id"]), [card], payload["model"], job_id)


def clear_cache() -> None:
    _CACHE.clear()
