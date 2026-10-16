"""Optional OpenRouter enrichment on top of the deterministic matcher."""

import asyncio
import hashlib
import json
import logging
import re
from uuid import UUID

from .ai_client import PROMPT_VERSION, AiCallError, AiCompletion, ai_available, complete_json, model_name
from .ai_schemas import (
    AiBulletTags,
    AiFamily,
    AiKeyword,
    AiRequirement,
    AiReview,
    AiSemantic,
    AiSuggestion,
)
from .job_match import analyze_requirements, match_qualifications
from .job_schemas import JobMatch
from .related_skills import DICTIONARY_PATH

logger = logging.getLogger("resume_engine.ai")

CATEGORIES = {
    "tool",
    "domain",
    "responsibility",
    "methodology",
    "credential",
    "degree",
    "experience_duration",
    "soft_skill",
}
CATEGORY_ALIASES = {
    "experience duration": "experience_duration",
    "soft skill": "soft_skill",
    "soft-skill": "soft_skill",
}
DETAILS = {
    "unavailable": "AI review is unavailable. The match score is unchanged.",
    "rate_limited": "The free model is rate limited. The match score is unchanged.",
    "invalid": "The model response could not be validated. The match score is unchanged.",
}
MIN_FAMILY_CONFIDENCE = 0.4
MIN_SEMANTIC_CONFIDENCE = 0.55
MAX_BULLETS = 40
MAX_SKILLS = 80
_CACHE: dict[str, dict] = {}
_CACHE_MAX = 32

_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s.-])?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?!\w)")

JOB_SYSTEM = """You categorise a job posting for a personal resume tool.
Return one JSON object with keys families, requirements, and keywords.
families: short job-family labels and confidence from 0 to 1.
requirements: one item per listed requirement. Copy its text, set group, choose one category, and set source_span to an exact quote from the posting.
keywords: extra tools or skills in the posting that are not already listed. Each needs a category and an exact source_span.
Categories: tool, domain, responsibility, methodology, credential, degree, experience_duration, soft_skill.
Do not invent text that is not in the posting. Ignore pay, benefits, and legal boilerplate."""

COMPARE_SYSTEM = """You compare unmatched job requirements with a redacted resume.
Return one JSON object with keys semantic_candidates, bullet_tags, and suggestions.
semantic_candidates: only when the resume already shows a genuine equivalent. resume_span must be an exact quote from the resume. confidence is from 0 to 1. Include a short rationale.
bullet_tags: tags for resume bullets you were given. bullet must be an exact quote. Use action, domain, skill, tool, outcome, and metric. Leave a tag empty when the bullet does not show it.
suggestions: a rewrite that only rephrases the quoted resume text for an unmatched requirement. resume_quote must be an exact quote. Do not add employers, tools, metrics, or experience that the quote does not show.
Do not claim a skill the resume does not show."""

JOB_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "families": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["label", "confidence"],
            },
        },
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "group": {"type": "string"},
                    "category": {"type": "string"},
                    "source_span": {"type": "string"},
                },
                "required": ["text", "group", "category", "source_span"],
            },
        },
        "keywords": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "keyword": {"type": "string"},
                    "category": {"type": "string"},
                    "source_span": {"type": "string"},
                },
                "required": ["keyword", "category", "source_span"],
            },
        },
    },
    "required": ["families", "requirements", "keywords"],
}

COMPARE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "semantic_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "requirement": {"type": "string"},
                    "resume_span": {"type": "string"},
                    "section": {"type": "string"},
                    "confidence": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": ["requirement", "resume_span", "confidence", "rationale"],
            },
        },
        "bullet_tags": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "bullet": {"type": "string"},
                    "section": {"type": "string"},
                    "action": {"type": "string"},
                    "domain": {"type": "string"},
                    "skill": {"type": "string"},
                    "tool": {"type": "string"},
                    "outcome": {"type": "string"},
                    "metric": {"type": "string"},
                },
                "required": ["bullet"],
            },
        },
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "requirement": {"type": "string"},
                    "resume_quote": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["requirement", "resume_quote", "suggestion"],
            },
        },
    },
    "required": ["semantic_candidates", "bullet_tags", "suggestions"],
}


def clear_cache() -> None:
    _CACHE.clear()


def taxonomy_version() -> str:
    return hashlib.sha256(DICTIONARY_PATH.read_bytes()).hexdigest()[:16]


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def span_in(haystack: str, needle: str) -> bool:
    quote = _compact(needle)
    if len(quote) < 2:
        return False
    return quote.casefold() in _compact(haystack).casefold()


def scrub(text: str, secrets: list[str]) -> str:
    value = text or ""
    for secret in sorted({item for item in secrets if len(item) >= 3}, key=len, reverse=True):
        value = re.sub(re.escape(secret), " ", value, flags=re.IGNORECASE)
    value = _EMAIL.sub(" ", value)
    value = _URL.sub(" ", value)
    value = _PHONE.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def _secrets(resume: dict) -> list[str]:
    header = resume.get("header") if isinstance(resume.get("header"), dict) else {}
    values = [
        header.get("name"),
        header.get("phone"),
        header.get("email"),
        header.get("linkedin_label"),
        header.get("linkedin_url"),
    ]
    for key in ("education", "work_experience", "leadership", "projects"):
        for item in resume.get(key) or []:
            if isinstance(item, dict):
                values.append(item.get("location"))
    for section in resume.get("custom_sections") or []:
        if not isinstance(section, dict):
            continue
        for entry in section.get("entries") or []:
            if isinstance(entry, dict):
                values.append(entry.get("location"))
    secrets = []
    for value in values:
        text = _text(value).strip()
        if len(text) < 3:
            continue
        secrets.append(text)
        for part in re.split(r"[,/|]", text):
            part = part.strip()
            if len(part) >= 3:
                secrets.append(part)
    return secrets


def redact_job(text: str) -> str:
    return scrub(text or "", [])


def _add_bullet(found: list[dict], seen: set[str], section: str, text: str, secrets: list[str]) -> None:
    cleaned = scrub(text, secrets)
    key = cleaned.casefold()
    if len(cleaned) < 8 or key in seen or len(found) >= MAX_BULLETS:
        return
    seen.add(key)
    found.append({"section": section or "Resume", "text": cleaned})


def redact_resume(resume: dict, bullets: list | None = None) -> dict:
    """Return skills and bullets with contact details removed."""
    resume = resume or {}
    secrets = _secrets(resume)
    skills: list[str] = []
    seen_skills: set[str] = set()
    for group in resume.get("tool_groups") or []:
        if not isinstance(group, dict):
            continue
        names = [_text(group.get("name")), *[_text(item) for item in group.get("items") or []]]
        for name in names:
            cleaned = scrub(name, secrets)
            key = cleaned.casefold()
            if not cleaned or key in seen_skills or len(skills) >= MAX_SKILLS:
                continue
            seen_skills.add(key)
            skills.append(cleaned)
    degrees = []
    for item in resume.get("education") or []:
        if not isinstance(item, dict):
            continue
        degree = scrub(_text(item.get("degree")), secrets)
        if degree and degree.casefold() not in {item.casefold() for item in degrees}:
            degrees.append(degree)
    roles = []
    for key in ("work_experience", "leadership", "projects"):
        for item in resume.get(key) or []:
            if not isinstance(item, dict):
                continue
            title = scrub(_text(item.get("title") or item.get("name")), secrets)
            if title and title.casefold() not in {role.casefold() for role in roles}:
                roles.append(title)
    found: list[dict] = []
    seen: set[str] = set()
    for item in bullets or []:
        if isinstance(item, dict):
            _add_bullet(found, seen, _text(item.get("section")) or "Resume", _text(item.get("wording")), secrets)
    for key, label in (
        ("work_experience", "Work Experience"),
        ("projects", "Projects"),
        ("leadership", "Leadership"),
    ):
        for item in resume.get(key) or []:
            if isinstance(item, dict):
                for bullet in item.get("bullets") or []:
                    _add_bullet(found, seen, label, _text(bullet), secrets)
    for group in resume.get("tool_groups") or []:
        if isinstance(group, dict):
            for bullet in group.get("bullets") or []:
                _add_bullet(found, seen, "Skills", _text(bullet), secrets)
    for item in resume.get("education") or []:
        if isinstance(item, dict):
            for bullet in item.get("bullets") or []:
                _add_bullet(found, seen, "Education", _text(bullet), secrets)
    return {
        "summary": scrub(_text(resume.get("summary")), secrets),
        "skills": skills,
        "degrees": degrees,
        "roles": roles,
        "bullets": found,
    }


def _category(value: str) -> str:
    compact = _norm(value).replace("-", "_").replace(" ", "_")
    if compact in CATEGORIES:
        return compact
    alias = CATEGORY_ALIASES.get(_norm(value).replace("-", " "), "")
    return alias if alias in CATEGORIES else ""


def _confidence(value, floor: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1 and number <= 100:
        number = number / 100
    if number < floor or number > 1:
        return None
    return number


def _review_rows(description: str, review: dict | None, match: dict) -> list[dict]:
    """Prefer matcher rows, then add any analysis row that is not already listed."""
    rows = []
    seen: set[str] = set()

    def add(text: str, group: str) -> None:
        key = _norm(text)
        if not key or key in seen:
            return
        seen.add(key)
        rows.append({"text": text, "group": group})

    for group in ("required", "preferred", "responsibilities"):
        for row in match.get(group) or []:
            if isinstance(row, dict):
                add(_text(row.get("text")), group)
    analysis = analyze_requirements(description, review)
    for group in ("required", "preferred", "responsibilities"):
        for row in analysis.get(group) or []:
            if isinstance(row, dict):
                add(_text(row.get("text")), group)
    return rows


def _match_requirement(text: str, rows: list[dict]) -> dict | None:
    norm = _norm(text)
    if not norm:
        return None
    exact = [row for row in rows if _norm(row["text"]) == norm]
    if len(exact) == 1:
        return exact[0]
    contained = []
    for row in rows:
        row_norm = _norm(row["text"])
        if len(norm) >= 12 and len(row_norm) >= 12 and (norm in row_norm or row_norm in norm):
            contained.append(row)
    if len(contained) == 1:
        return contained[0]
    return None


def _filter_job(payload: dict, job_text: str, rows: list[dict]) -> dict:
    families = []
    seen_families: set[str] = set()
    dropped = 0
    for item in payload.get("families") or []:
        if not isinstance(item, dict):
            dropped += 1
            continue
        label = _compact(_text(item.get("label")))
        confidence = _confidence(item.get("confidence"), MIN_FAMILY_CONFIDENCE)
        key = label.casefold()
        if not label or len(label) > 80 or confidence is None or key in seen_families:
            dropped += 1
            continue
        seen_families.add(key)
        families.append({"label": label, "confidence": confidence})
        if len(families) >= 6:
            break

    requirements = []
    seen_requirements: set[str] = set()
    for item in payload.get("requirements") or []:
        if not isinstance(item, dict):
            dropped += 1
            continue
        span = _text(item.get("source_span"))
        category = _category(_text(item.get("category")))
        if not category or not span_in(job_text, span):
            dropped += 1
            continue
        known = _match_requirement(_text(item.get("text")), rows)
        if known:
            if not (span_in(span, known["text"]) or span_in(known["text"], span)):
                dropped += 1
                continue
            text = known["text"]
            group = known["group"]
        else:
            text = _compact(_text(item.get("text")))
            group = _text(item.get("group"))
            if group == "responsibility":
                group = "responsibilities"
            if group not in {"required", "preferred", "responsibilities"} or not span_in(span, text):
                dropped += 1
                continue
        key = _norm(text)
        if not key or key in seen_requirements:
            dropped += 1
            continue
        seen_requirements.add(key)
        requirements.append(
            {"text": text, "group": group, "category": category, "source_span": _compact(span)}
        )
        if len(requirements) >= 40:
            break

    keywords = []
    seen_keywords: set[str] = set()
    for item in payload.get("keywords") or []:
        if not isinstance(item, dict):
            dropped += 1
            continue
        keyword = _compact(_text(item.get("keyword")))
        span = _text(item.get("source_span"))
        category = _category(_text(item.get("category")))
        if not category or not keyword or not span_in(job_text, span) or not span_in(span, keyword):
            dropped += 1
            continue
        key = keyword.casefold()
        if key in seen_keywords:
            dropped += 1
            continue
        seen_keywords.add(key)
        keywords.append({"keyword": keyword, "category": category, "source_span": _compact(span)})
        if len(keywords) >= 30:
            break
    return {
        "families": families,
        "requirements": requirements,
        "keywords": keywords,
        "dropped": dropped,
    }


def _resume_corpus(resume: dict) -> str:
    parts = [
        _text(resume.get("summary")),
        *[_text(item) for item in resume.get("skills") or []],
        *[_text(item) for item in resume.get("degrees") or []],
        *[_text(item) for item in resume.get("roles") or []],
    ]
    for bullet in resume.get("bullets") or []:
        if isinstance(bullet, dict):
            parts.append(_text(bullet.get("text")))
    return "\n".join(part for part in parts if part)


def _unmatched(match: dict) -> list[dict]:
    rows = []
    for group in ("required", "preferred", "responsibilities"):
        for row in match.get(group) or []:
            if isinstance(row, dict) and not row.get("matched") and _text(row.get("text")):
                rows.append({"text": row["text"], "group": group})
    return rows


def _filter_comparison(payload: dict, unmatched: list[dict], resume: dict) -> dict:
    corpus = _resume_corpus(resume)
    bullets = [item for item in resume.get("bullets") or [] if isinstance(item, dict)]
    bullet_by_text = {_norm(_text(item.get("text"))): item for item in bullets}
    sections = {_norm(_text(item.get("section"))) for item in bullets}
    dropped = 0

    semantic = []
    seen_semantic: set[str] = set()
    for item in payload.get("semantic_candidates") or []:
        if not isinstance(item, dict):
            dropped += 1
            continue
        span = _text(item.get("resume_span"))
        confidence = _confidence(item.get("confidence"), MIN_SEMANTIC_CONFIDENCE)
        known = _match_requirement(_text(item.get("requirement")), unmatched)
        if known is None or confidence is None or not span_in(corpus, span):
            dropped += 1
            continue
        key = _norm(known["text"])
        if key in seen_semantic:
            dropped += 1
            continue
        seen_semantic.add(key)
        section = _compact(_text(item.get("section")))
        if _norm(section) not in sections:
            section = ""
        semantic.append(
            {
                "requirement": known["text"],
                "resume_span": _compact(span),
                "section": section,
                "confidence": confidence,
                "rationale": _compact(_text(item.get("rationale")))[:400],
            }
        )
        if len(semantic) >= 20:
            break

    tags = []
    seen_bullets: set[str] = set()
    for item in payload.get("bullet_tags") or []:
        if not isinstance(item, dict):
            dropped += 1
            continue
        known_bullet = bullet_by_text.get(_norm(_text(item.get("bullet"))))
        if known_bullet is None:
            dropped += 1
            continue
        fields = {
            name: _compact(_text(item.get(name)))[:120]
            for name in ("action", "domain", "skill", "tool", "outcome", "metric")
        }
        if not any(fields.values()):
            dropped += 1
            continue
        key = _norm(known_bullet["text"])
        if key in seen_bullets:
            dropped += 1
            continue
        seen_bullets.add(key)
        tags.append({"bullet": known_bullet["text"], "section": known_bullet.get("section") or "", **fields})
        if len(tags) >= MAX_BULLETS:
            break

    suggestions = []
    for item in payload.get("suggestions") or []:
        if not isinstance(item, dict):
            dropped += 1
            continue
        quote = _text(item.get("resume_quote"))
        suggestion = _compact(_text(item.get("suggestion")))
        if not suggestion or not span_in(corpus, quote):
            dropped += 1
            continue
        known = _match_requirement(_text(item.get("requirement")), unmatched)
        requirement = known["text"] if known else ""
        if not requirement:
            dropped += 1
            continue
        suggestions.append(
            {"requirement": requirement, "resume_quote": _compact(quote), "suggestion": suggestion[:500]}
        )
        if len(suggestions) >= 12:
            break
    return {
        "semantic_candidates": semantic,
        "bullet_tags": tags,
        "suggestions": suggestions,
        "dropped": dropped,
    }


def _cache_key(job_text: str, resume: dict, revision: int, review: dict, model: str) -> str:
    payload = {
        "job": job_text,
        "resume": resume,
        "revision": revision,
        "review": review or {},
        "prompt": PROMPT_VERSION,
        "model": model,
        "taxonomy": taxonomy_version(),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _remember(key: str, value: dict) -> None:
    _CACHE[key] = value
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))


def _pack(
    composition_id: UUID,
    match: dict,
    status: str,
    model: str = "",
    job_part: dict | None = None,
    compare_part: dict | None = None,
) -> dict:
    job_part = job_part or {}
    compare_part = compare_part or {}
    review = AiReview(
        composition_id=composition_id,
        status=status,
        detail=DETAILS.get(status, ""),
        model=model,
        match=JobMatch.model_validate({**match, "composition_id": composition_id}),
        families=[AiFamily.model_validate(item) for item in job_part.get("families") or []],
        requirements=[AiRequirement.model_validate(item) for item in job_part.get("requirements") or []],
        keywords=[AiKeyword.model_validate(item) for item in job_part.get("keywords") or []],
        semantic_candidates=[
            AiSemantic.model_validate(item) for item in compare_part.get("semantic_candidates") or []
        ],
        bullet_tags=[AiBulletTags.model_validate(item) for item in compare_part.get("bullet_tags") or []],
        suggestions=[AiSuggestion.model_validate(item) for item in compare_part.get("suggestions") or []],
    )
    return review.model_dump(mode="json")


def _log_validation(model: str, outcome: str, job_part: dict, compare_part: dict) -> None:
    logger.info(
        "model=%s prompt=%s outcome=%s kept_requirements=%s dropped_requirements=%s kept_keywords=%s kept_semantic=%s kept_suggestions=%s",
        model,
        PROMPT_VERSION,
        outcome,
        len(job_part.get("requirements") or []),
        int(job_part.get("dropped") or 0) + int(compare_part.get("dropped") or 0),
        len(job_part.get("keywords") or []),
        len(compare_part.get("semantic_candidates") or []),
        len(compare_part.get("suggestions") or []),
    )


async def review_resume(
    composition_id: UUID,
    description: str,
    resume: dict,
    bullets: list | None = None,
    review: dict | None = None,
    revision: int = 0,
    complete=None,
) -> dict:
    """Return a validated review. The match counts stay deterministic."""
    review = review or {}
    match = match_qualifications(description or "", resume or {}, bullets, review)
    match["composition_id"] = composition_id
    model = model_name()
    if complete is None:
        complete = complete_json
        if not ai_available():
            _log_validation(model, "unavailable", {}, {})
            return _pack(composition_id, match, "unavailable")

    redacted_job = redact_job(description or "")
    redacted_resume = redact_resume(resume or {}, bullets)
    key = _cache_key(redacted_job, redacted_resume, revision, review, model)
    cached = _CACHE.get(key)
    if cached is not None:
        payload = json.loads(json.dumps(cached))
        payload["composition_id"] = str(composition_id)
        payload["match"]["composition_id"] = str(composition_id)
        return payload

    rows = _review_rows(redacted_job, review, match)
    unmatched = _unmatched(match)
    job_messages = [
        {"role": "system", "content": JOB_SYSTEM},
        {
            "role": "user",
            "content": json.dumps(
                {"posting": redacted_job[:12000], "requirements": rows[:40]},
                ensure_ascii=False,
            ),
        },
    ]
    tasks = [asyncio.create_task(_complete(complete, job_messages, JOB_SCHEMA, "job_review"))]
    compare_messages = None
    if unmatched or redacted_resume.get("bullets"):
        compare_messages = [
            {"role": "system", "content": COMPARE_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {"unmatched_requirements": unmatched[:40], "resume": redacted_resume},
                    ensure_ascii=False,
                ),
            },
        ]
        tasks.append(asyncio.create_task(_complete(complete, compare_messages, COMPARE_SCHEMA, "resume_comparison")))
    results = await asyncio.gather(*tasks)
    job_result = results[0]
    compare_result = results[1] if compare_messages is not None else None

    job_part = {"families": [], "requirements": [], "keywords": [], "dropped": 0}
    compare_part = {"semantic_candidates": [], "bullet_tags": [], "suggestions": [], "dropped": 0}
    served = model
    errors: list[AiCallError] = []
    if isinstance(job_result, AiCallError):
        errors.append(job_result)
    elif isinstance(job_result, AiCompletion):
        job_part = _filter_job(job_result.data, redacted_job, rows)
        served = job_result.model or served
    if isinstance(compare_result, AiCallError):
        errors.append(compare_result)
    elif isinstance(compare_result, AiCompletion):
        compare_part = _filter_comparison(compare_result.data, unmatched, redacted_resume)
        served = compare_result.model or served

    if errors and not any(isinstance(item, AiCompletion) for item in (job_result, compare_result)):
        status = _status_from(errors)
        _log_validation(served, status, job_part, compare_part)
        return _pack(composition_id, match, status, model=served, job_part=job_part, compare_part=compare_part)

    _log_validation(served, "ok", job_part, compare_part)
    payload = _pack(
        composition_id,
        match,
        "ok",
        model=served,
        job_part=job_part,
        compare_part=compare_part,
    )
    _remember(key, payload)
    return json.loads(json.dumps(payload))


async def _complete(complete, messages, schema, name):
    try:
        result = await complete(messages, schema, name)
    except AiCallError as exc:
        return exc
    if not isinstance(getattr(result, "data", None), dict):
        return AiCallError("invalid")
    return result


def _status_from(errors: list[AiCallError]) -> str:
    statuses = {exc.status for exc in errors}
    for status in ("rate_limited", "invalid", "unavailable"):
        if status in statuses:
            return status
    return "unavailable"
