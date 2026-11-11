"""AI reading of one job posting, run only when the user asks. The result is saved on the job.

Only the posting is sent, never a resume. Every requirement the model returns must quote the
posting exactly (source_span), and every keyword must appear inside its quote, so each one can be
highlighted in the posting and nothing invented gets through. Requirements the rule-based parser
did not find are added to matching at a lower weight until the user accepts them
(job_match.apply_ai).
"""

import hashlib
import logging
import re
from datetime import datetime, timezone

from .ai_client import AiCallError, ai_available, complete_json, model_name
from .ai_review import redact_job, span_in

logger = logging.getLogger("resume_engine.ai")

ANALYSIS_VERSION = "1"
MAX_POSTING = 16000
MAX_REQUIREMENTS = 45
MAX_KEYWORDS = 5
MAX_SPAN = 600
MAX_KEYWORD = 60
GROUPS = {"required", "preferred", "responsibility"}
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
DETAILS = {
    "unavailable": "AI analysis is unavailable right now. The rule-based requirements still work.",
    "rate_limited": "The AI model is rate limited. Try again in a minute.",
    "invalid": "The AI response could not be checked against the posting. Try again.",
}

SYSTEM = """You read a job posting for a job seeker and list what the employer asks for.
Return one JSON object with key requirements: one item for every distinct requirement, qualification, or responsibility in the posting.
Each item has:
- source_span: the requirement copied exactly from the posting, character for character (one bullet or one sentence).
- group: "required", "preferred" (nice to have, a plus, ideally, bonus, preferred), or "responsibility" (what the person will do in the job).
- category: one of tool, domain, responsibility, methodology, credential, degree, experience_duration, soft_skill.
- keywords: 1 to 5 short skill terms a resume could show, each copied exactly from inside source_span (e.g. "SQL", "stakeholder management", "fire codes"). Use the posting's own words.
- match_mode: "any" when one of the keywords is enough ("AWS, GCP, or Azure"), otherwise "all".
Include soft skills and behaviours ("translate analysis into clear insights for leaders"), not only tools.
Skip the company introduction, pay, benefits, schedules, locations, legal and equal-opportunity text.
Never invent or paraphrase text: copy it."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source_span": {"type": "string"},
                    "group": {"type": "string"},
                    "category": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "match_mode": {"type": "string"},
                },
                "required": ["source_span", "group", "category", "keywords"],
            },
        }
    },
    "required": ["requirements"],
}

_PAY = re.compile(r"\$\s?\d|per (?:year|hour|annum)|hiring range|salary|equal opportunity|benefits", re.IGNORECASE)


def body_hash(body: str) -> str:
    """Analysis is kept only while the posting text is the one that was analysed."""
    return hashlib.sha256(" ".join((body or "").split()).encode("utf-8")).hexdigest()[:32]


def is_current(analysis, body: str) -> bool:
    return isinstance(analysis, dict) and analysis.get("body_hash") == body_hash(body) and bool(analysis.get("requirements"))


def _clip(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _exact(posting: str, span: str) -> str:
    """The posting's own text for a quote the model copied (whitespace and case may differ),
    so the highlight shows exactly what the posting says."""
    words = [re.escape(word) for word in span.split()]
    if not words:
        return ""
    match = re.search(r"\s+".join(words), posting, re.IGNORECASE)
    return " ".join(match.group(0).split()) if match else ""


def validate(payload, posting: str) -> tuple[list[dict], int]:
    """Keep only requirements quoted from the posting, with keywords from inside each quote."""
    kept: list[dict] = []
    seen: set[str] = set()
    dropped = 0
    items = payload.get("requirements") if isinstance(payload, dict) else None
    for item in items or []:
        if not isinstance(item, dict):
            dropped += 1
            continue
        span = _clip(item.get("source_span"), MAX_SPAN + 1).strip(" -•*")
        if not span or len(span) > MAX_SPAN or len(span) < 3 or not span_in(posting, span) or _PAY.search(span):
            dropped += 1
            continue
        span = _exact(posting, span) or span
        key = span.casefold()
        if key in seen:
            continue
        group = _clip(item.get("group"), 20).lower()
        group = "responsibility" if group.startswith("respons") else group
        if group not in GROUPS:
            group = "required"
        category = _clip(item.get("category"), 30).lower().replace(" ", "_").replace("-", "_")
        if category not in CATEGORIES:
            category = "responsibility" if group == "responsibility" else "domain"
        keywords: list[str] = []
        for raw in item.get("keywords") or []:
            keyword = _clip(raw, MAX_KEYWORD + 1).strip(" .,;:()")
            if not keyword or len(keyword) > MAX_KEYWORD or not span_in(span, keyword):
                continue
            keyword = _exact(span, keyword) or keyword
            if keyword.casefold() not in {existing.casefold() for existing in keywords}:
                keywords.append(keyword)
            if len(keywords) >= MAX_KEYWORDS:
                break
        if not keywords and category not in {"degree", "experience_duration", "credential"}:
            dropped += 1
            continue
        mode = "any" if _clip(item.get("match_mode"), 5).lower() == "any" and len(keywords) > 1 else "all"
        seen.add(key)
        kept.append({"text": span, "group": group, "category": category, "keywords": keywords, "match_mode": mode})
        if len(kept) >= MAX_REQUIREMENTS:
            break
    return kept, dropped


def posting_for_model(body: str) -> str:
    """Contact details removed line by line, so the model still sees headings and bullets."""
    lines = [redact_job(line) for line in (body or "").splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()[:MAX_POSTING]


async def analyze_job(body: str, complete=None) -> dict:
    """Return {status, detail, analysis}. analysis is what the job stores, or None on failure."""
    model = model_name()
    if complete is None:
        complete = complete_json
        if not ai_available():
            return {"status": "unavailable", "detail": DETAILS["unavailable"], "analysis": None}
    posting = posting_for_model(body)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": posting}]
    try:
        completion = await complete(messages, SCHEMA, "job_analysis")
    except AiCallError as exc:
        logger.info("job_analysis prompt=%s outcome=%s", ANALYSIS_VERSION, exc.status)
        return {"status": exc.status, "detail": DETAILS.get(exc.status, DETAILS["unavailable"]), "analysis": None}
    # Checked against the posting as saved, so every quote can be highlighted there.
    requirements, dropped = validate(getattr(completion, "data", None), body or "")
    served = getattr(completion, "model", "") or model
    logger.info("job_analysis prompt=%s outcome=%s kept=%s dropped=%s model=%s", ANALYSIS_VERSION, "ok" if requirements else "invalid", len(requirements), dropped, served)
    if not requirements:
        return {"status": "invalid", "detail": DETAILS["invalid"], "analysis": None}
    return {
        "status": "ok",
        "detail": "",
        "analysis": {
            "version": ANALYSIS_VERSION,
            "body_hash": body_hash(body),
            "model": served,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "requirements": requirements,
            "dropped": dropped,
        },
    }
