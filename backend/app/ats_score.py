"""Deterministic ATS-style score for one resume against one job.

Modeled on how common applicant tracking systems parse and rank resumes: keyword coverage,
hard requirements, title match, where keywords appear, whether the file parses cleanly, and
length. The same inputs always give the same score. No AI is involved.
"""

import re

DISCLAIMER = (
    "This is an estimate modeled on how common applicant tracking systems parse and rank "
    "resumes. Employers configure their systems differently, so your score in an employer's "
    "system may differ. It is not a guarantee of ranking or interview."
)

WEIGHTS = {
    "keywords": 35,
    "requirements": 20,
    "title": 10,
    "context": 10,
    "parsing": 15,
    "length": 10,
}

METHODOLOGY = [
    {
        "id": "keywords",
        "label": "Keyword match",
        "weight": WEIGHTS["keywords"],
        "rule": "Share of the job's keywords found in the resume. Required keywords count twice as much as preferred ones.",
        "why": "Most ATS search and rank on exact or near-exact keyword matches before a person reads the resume.",
    },
    {
        "id": "requirements",
        "label": "Required qualifications",
        "weight": WEIGHTS["requirements"],
        "rule": "Weighted coverage of required lines (60%) plus degree, years and certification checks (40%; pass 1, unknown 0.5, fail 0).",
        "why": "Knockout questions and required-qualification filters remove resumes before ranking.",
    },
    {
        "id": "title",
        "label": "Job title alignment",
        "weight": WEIGHTS["title"],
        "rule": "Word overlap between the job title and the resume's display title, target role, and most recent job title.",
        "why": "Recruiters often search by title, and many ATS weight a matching recent title.",
    },
    {
        "id": "context",
        "label": "Keyword context",
        "weight": WEIGHTS["context"],
        "rule": "Share of matched keywords that appear in Experience, Projects or Leadership bullets, not only in the Skills list.",
        "why": "Keywords backed by work history rank higher in several ATS and read as evidence to reviewers.",
    },
    {
        "id": "parsing",
        "label": "Parseability",
        "weight": WEIGHTS["parsing"],
        "rule": "Standard Experience, Education and Skills sections; email and phone present; dates on each role. Table-based layouts lose points.",
        "why": "An ATS has to extract fields correctly before it can match anything.",
    },
    {
        "id": "length",
        "label": "Length and bullets",
        "weight": WEIGHTS["length"],
        "rule": "One or two pages; bullets of 8 to 35 words; bullets that include a number or measurable result.",
        "why": "Concise, quantified bullets parse cleanly and score better with reviewers.",
    },
]

_WORD = re.compile(r"[a-z0-9+#]+")
_STOP = {"and", "or", "the", "a", "an", "of", "for", "to", "in", "with", "at", "on", "sr", "jr", "i", "ii", "iii"}
_NUMBER = re.compile(r"\d")
BULLET_SECTIONS = {"Work Experience", "Projects", "Leadership"}


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _tokens(text: str) -> set[str]:
    return {word for word in _WORD.findall((text or "").lower()) if word not in _STOP}


def _rows(match: dict, group: str) -> list[dict]:
    return [row for row in match.get(group) or [] if isinstance(row, dict)]


def _component(cid: str, ratio: float, detail: str, tips: list[str]) -> dict:
    ratio = max(0.0, min(1.0, ratio))
    weight = WEIGHTS[cid]
    label = next(item["label"] for item in METHODOLOGY if item["id"] == cid)
    return {
        "id": cid,
        "label": label,
        "weight": weight,
        "earned": round(weight * ratio, 1),
        "ratio": round(ratio, 3),
        "detail": detail,
        "tips": tips,
    }


def _keywords(match: dict) -> dict:
    total = found = 0.0
    missing: list[str] = []
    skipped: set[str] = set()
    for group, weight in (("required", 2.0), ("preferred", 1.0)):
        for row in _rows(match, group):
            for item in row.get("keywords") or []:
                total += weight
                if item.get("found") or row.get("manual"):
                    found += weight
                elif item.get("skipped"):
                    # The user said they lack it: it still counts as missing, but isn't a tip.
                    skipped.add((item.get("keyword") or "").lower())
                elif group == "required":
                    missing.append(item.get("keyword") or "")
    if total == 0:
        return _component("keywords", 1.0, "The job lists no keywords to match.", [])
    ratio = found / total
    tips = []
    if missing:
        names = ", ".join(sorted({name for name in missing if name})[:4])
        tips.append(f"Add missing required keywords where they are true: {names}.")
    skipped.discard("")
    if skipped:
        count = len(skipped)
        noun = "keyword" if count == 1 else "keywords"
        tips.append(f"{count} {noun} you marked as not your experience still count as missing.")
    return _component("keywords", ratio, f"{round(ratio * 100)}% of weighted keywords found.", tips)


def _requirements(match: dict) -> dict:
    coverage = float((match.get("scores") or {}).get("required_coverage") or 0)
    required = _rows(match, "required")
    if not required:
        coverage = 1.0
    gates = match.get("eligibility") or {}
    gate_values = []
    failed = []
    for key in ("degree", "years", "certification"):
        status = (gates.get(key) or {}).get("status", "not_stated")
        if status == "not_stated":
            continue
        gate_values.append({"pass": 1.0, "unknown": 0.5}.get(status, 0.0))
        if status == "fail":
            failed.append(key)
    gate_ratio = sum(gate_values) / len(gate_values) if gate_values else 1.0
    ratio = coverage * 0.6 + gate_ratio * 0.4
    matched = sum(1 for row in required if row.get("matched"))
    detail = f"{matched} of {len(required)} required lines matched."
    if gate_values:
        detail += f" Degree, years and certification: {len(gate_values) - len(failed)} of {len(gate_values)} met or unclear."
    tips = []
    if required and matched < len(required):
        tips.append("Cover each required line in a bullet or the Skills section, using the job's wording where it is true.")
    if failed:
        tips.append(f"Check the {', '.join(failed)} requirement; state it plainly if you meet it.")
    return _component("requirements", ratio, detail, tips)


def _title(job: dict, composition: dict, resume: dict) -> dict:
    wanted = _tokens(_text(job.get("role")) or _text(job.get("title")))
    if not wanted:
        return _component("title", 1.0, "The job has no title to compare.", [])
    candidates = [
        _text(composition.get("display_title")),
        _text(composition.get("target_role")),
    ]
    work = resume.get("work_experience") or []
    if work and isinstance(work[0], dict):
        candidates.append(_text(work[0].get("title")))
    best = max((len(wanted & _tokens(text)) / len(wanted) for text in candidates if text), default=0.0)
    tips = []
    if best < 1:
        tips.append("Use the job's title in the resume headline or display title if it describes you accurately.")
    return _component("title", best, f"{round(best * 100)}% of the job title's words appear in your titles.", tips)


def _context(match: dict) -> dict:
    found = backed = 0
    for group in ("required", "preferred"):
        for row in _rows(match, group):
            for item in row.get("keywords") or []:
                if not item.get("found"):
                    continue
                found += 1
                evidence = item.get("evidence") or {}
                where = item.get("where") or evidence.get("section") or ""
                if where in BULLET_SECTIONS:
                    backed += 1
    if not found:
        return _component("context", 0.0, "No matched keywords yet.", ["Match keywords first, then back them with bullets."])
    ratio = backed / found
    tips = []
    if ratio < 1:
        tips.append("Show key skills inside Experience or Project bullets, not only in the Skills list.")
    return _component("context", ratio, f"{backed} of {found} matched keywords appear in experience bullets.", tips)


def _parsing(resume: dict, composition: dict) -> dict:
    checks = []
    tips = []
    header = resume.get("header") if isinstance(resume.get("header"), dict) else {}
    work = [item for item in resume.get("work_experience") or [] if isinstance(item, dict)]
    sections = {
        "Experience": bool(work or resume.get("projects")),
        "Education": bool(resume.get("education")),
        "Skills": bool(resume.get("tool_groups")),
    }
    for name, present in sections.items():
        checks.append(present)
        if not present:
            tips.append(f"Add a standard {name} section.")
    has_contact = bool(_text(header.get("email")).strip()) and bool(_text(header.get("phone")).strip())
    checks.append(has_contact)
    if not has_contact:
        tips.append("Include both email and phone in the header.")
    dated = all(_text(item.get("date") or item.get("date_label")).strip() for item in work) if work else False
    checks.append(dated)
    if not dated:
        tips.append("Give every role a date range.")
    ratio = sum(checks) / len(checks)
    detail = f"{sum(checks)} of {len(checks)} parsing checks pass."
    if (composition.get("template_style") or "") == "sre":
        ratio = max(0.0, ratio - 5 / WEIGHTS["parsing"])
        detail += " The Skill Table template uses a table, which some ATS read poorly."
        tips.append("Prefer a single-column template without tables when applying through an ATS.")
    return _component("parsing", ratio, detail, tips)


def _bullets(resume: dict) -> list[str]:
    found = []
    for key in ("work_experience", "projects", "leadership"):
        for item in resume.get(key) or []:
            if isinstance(item, dict):
                found.extend(_text(bullet) for bullet in item.get("bullets") or [] if _text(bullet).strip())
    return found


def _length(resume: dict, page_count: int | None) -> dict:
    bullets = _bullets(resume)
    tips = []
    parts = []
    if page_count:
        page_ok = 1.0 if page_count <= 2 else max(0.0, 1 - (page_count - 2) * 0.5)
        parts.append(page_ok)
        if page_ok < 1:
            tips.append("Trim to two pages or fewer.")
    if bullets:
        sized = sum(1 for bullet in bullets if 8 <= len(bullet.split()) <= 35) / len(bullets)
        numbered = sum(1 for bullet in bullets if _NUMBER.search(bullet)) / len(bullets)
        parts.extend([sized, min(1.0, numbered / 0.5)])
        if sized < 0.8:
            tips.append("Keep bullets between 8 and 35 words.")
        if numbered < 0.5:
            tips.append("Add a measurable result to more bullets where you have one.")
        detail = f"{len(bullets)} bullets; {round(sized * 100)}% well sized, {round(numbered * 100)}% quantified."
    else:
        parts.append(0.0)
        tips.append("Add bullets to your roles.")
        detail = "No experience bullets found."
    if page_count:
        detail = f"{page_count} page{'s' if page_count != 1 else ''}. " + detail
    return _component("length", sum(parts) / len(parts), detail, tips)


def band(score: float) -> str:
    if score >= 75:
        return "Strong"
    if score >= 55:
        return "Fair"
    return "Needs work"


def score_resume(match: dict, resume: dict, job: dict, composition: dict, page_count: int | None = None) -> dict:
    """Return the score, one row per component with tips, the methodology and the disclaimer."""
    resume = resume or {}
    components = [
        _keywords(match),
        _requirements(match),
        _title(job or {}, composition or {}, resume),
        _context(match),
        _parsing(resume, composition or {}),
        _length(resume, page_count),
    ]
    score = round(sum(item["earned"] for item in components))
    return {
        "score": score,
        "band": band(score),
        "components": components,
        "methodology": METHODOLOGY,
        "disclaimer": DISCLAIMER,
    }
