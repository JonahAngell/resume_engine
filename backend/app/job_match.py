"""Compare job-description keywords with the text of a saved resume."""

import re
from dataclasses import dataclass

from .related_skills import combination_mention, related_mention

MAX_KEYWORDS = 40

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "with", "at", "by",
    "from", "as", "is", "are", "be", "was", "were", "been", "being", "our", "your",
    "you", "we", "they", "their", "this", "that", "these", "those", "it", "its",
    "will", "can", "may", "must", "should", "able", "ability", "experience",
    "experienced", "experiences", "years", "year", "team", "teams", "strong",
    "including", "include", "includes", "preferred", "required", "requirement",
    "requirements", "responsibilities", "responsibility", "qualifications",
    "qualification", "role", "job", "work", "working", "skills", "skill",
    "knowledge", "plus", "etc", "using", "use", "used", "across", "within", "into",
    "over", "about", "such", "other", "both", "all", "any", "not", "no", "well",
    "high", "looking", "seek", "seeking", "candidate", "candidates", "position",
    "positions", "opportunity", "company", "environment", "join", "apply",
    "application", "benefits", "equal", "employer", "related", "relevant",
    "minimum", "least", "more", "than", "per", "via", "who", "what", "when",
    "where", "which", "while", "also", "have", "has", "had", "having", "do",
    "does", "did", "done", "make", "makes", "making", "help", "helps", "need",
    "needs", "needed", "please", "based", "level", "levels", "senior", "junior",
    "staff", "proven", "demonstrated", "successful", "success", "excellent",
    "great", "good", "best", "new", "fast", "paced", "day", "today", "various",
    "multiple", "wide", "range", "hands",
}

ACRONYM_SKIP = {"US", "AM", "PM", "EOE", "TBD", "II", "III", "IV"}

CAPITAL_TERM = re.compile(
    r"\b(?:[A-Z]{2,}(?:/[A-Z]{2,})*|[A-Z][A-Za-z0-9+#.]{1,})(?:\s+(?:[A-Z]{2,}(?:/[A-Z]{2,})*|[A-Z][A-Za-z0-9+#.]{1,})){0,2}"
)
SPECIAL_TERM = re.compile(r"(?<![\w.])(?:\.NET|C\+\+|C#)(?![\w#])", re.IGNORECASE)
WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.]{1,}")


@dataclass
class Candidate:
    keyword: str
    score: int
    position: int


def extract_keywords(text: str) -> list[dict]:
    """Return up to 40 distinctive keywords in the order they first appear."""
    found: dict[str, Candidate] = {}

    def add(keyword: str, score: int, position: int) -> None:
        cleaned = _clean_phrase(keyword)
        if not cleaned or _all_stopwords(cleaned):
            return
        key = cleaned.lower()
        current = found.get(key)
        if current is None:
            found[key] = Candidate(cleaned, score, position)
            return
        current.score = max(current.score, score)
        current.position = min(current.position, position)
        if _casing_score(cleaned) > _casing_score(current.keyword):
            current.keyword = cleaned

    for match in SPECIAL_TERM.finditer(text):
        add(match.group(0), 8, match.start())
    for match in CAPITAL_TERM.finditer(text):
        phrase = match.group(0)
        words = phrase.split()
        if len(words) == 1 and not _is_acronym(words[0]):
            if _sentence_start(text, match.start()) and not _line_is_term(text, match.start(), match.end()):
                continue
        if len(words) == 1 and _is_acronym(words[0]) and words[0] in ACRONYM_SKIP:
            continue
        add(phrase, 8 if len(words) == 1 and _is_acronym(words[0]) else 6, match.start())
    for phrase, position in _comma_lists(text):
        add(phrase, 7, position)
    for phrase, position, frequency in _repeated_phrases(text):
        add(phrase, frequency, position)

    ordered = sorted(found.values(), key=lambda item: (-len(_tokens(item.keyword)), -item.score, item.position))
    chosen: list[Candidate] = []
    chosen_tokens: list[tuple[str, ...]] = []
    for candidate in ordered:
        tokens = _tokens(candidate.keyword)
        if not tokens:
            continue
        if any(tokens == existing or _covers(existing, tokens) for existing in chosen_tokens):
            continue
        chosen.append(candidate)
        chosen_tokens.append(tokens)
        if len(chosen) >= MAX_KEYWORDS:
            break
    chosen.sort(key=lambda item: item.position)
    return [{"keyword": item.keyword, "kind": _kind(item.keyword)} for item in chosen]


def match_resume(description: str, resume: dict) -> dict:
    """Report which extracted keywords already appear in the resume."""
    keywords = extract_keywords(description or "")
    sections = _section_texts(resume or {})
    included = []
    missing = []
    for item in keywords:
        section = _find_section(item["keyword"], sections)
        if section:
            included.append({"keyword": item["keyword"], "section": section, "suggestion": ""})
        else:
            label = "Work Experience" if item["kind"] == "responsibility" else "Skills"
            missing.append(
                {
                    "keyword": item["keyword"],
                    "section": label,
                    "suggestion": _suggestion(item["keyword"], item["kind"]),
                }
            )
    return {
        "keyword_count": len(keywords),
        "included_count": len(included),
        "missing_count": len(missing),
        "included": included,
        "missing": missing,
    }


def _suggestion(keyword: str, kind: str) -> str:
    if kind == "responsibility":
        return f'Add "{keyword}" to a Work Experience bullet only where it is true.'
    return f'Add "{keyword}" to Skills if you use it.'


def _kind(keyword: str) -> str:
    return "responsibility" if len(keyword.split()) >= 3 else "skill"


def _section_texts(resume: dict) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    skill_bits = []
    for group in resume.get("tool_groups") or []:
        skill_bits.append(_text(group.get("name")))
        skill_bits.extend(_text(item) for item in group.get("items") or [])
        skill_bits.extend(_text(item) for item in group.get("bullets") or [])
    if any(bit.strip() for bit in skill_bits):
        sections.append(("Skills", "\n".join(skill_bits)))
    summary = _text(resume.get("summary"))
    if summary.strip():
        sections.append(("Summary", summary))
    for key, label, fields in (
        ("work_experience", "Work Experience", ("organization", "title")),
        ("projects", "Projects", ("name", "subtitle")),
        ("leadership", "Leadership", ("organization", "title")),
    ):
        bits = []
        for item in resume.get(key) or []:
            bits.extend(_text(item.get(field)) for field in fields)
            bits.extend(_text(bullet) for bullet in item.get("bullets") or [])
        if any(bit.strip() for bit in bits):
            sections.append((label, "\n".join(bits)))
    education_bits = []
    for item in resume.get("education") or []:
        education_bits.extend(
            _text(item.get(field)) for field in ("institution", "degree", "degree_type", "degree_major")
        )
        education_bits.extend(_text(bullet) for bullet in item.get("bullets") or [])
    if any(bit.strip() for bit in education_bits):
        sections.append(("Education", "\n".join(education_bits)))
    interest_bits = [_text(item) for item in resume.get("personal_interests") or []]
    for item in resume.get("personal_interest_items") or []:
        if isinstance(item, dict):
            interest_bits.append(_text(item.get("body") or item.get("text")))
        else:
            interest_bits.append(_text(item))
    for bullets in (resume.get("interest_bullets") or {}).values():
        interest_bits.extend(_text(bullet) for bullet in bullets or [])
    if any(bit.strip() for bit in interest_bits):
        sections.append(("Personal Interests", "\n".join(interest_bits)))
    for section in resume.get("custom_sections") or []:
        bits = [_text(section.get("title"))]
        for entry in section.get("entries") or []:
            bits.extend(
                _text(entry.get(field)) for field in ("primary_text", "secondary_text")
            )
            bits.extend(_text(bullet) for bullet in entry.get("bullets") or [])
        if any(bit.strip() for bit in bits):
            sections.append((_text(section.get("title")) or "Custom", "\n".join(bits)))
    return sections


def _find_section(keyword: str, sections: list[tuple[str, str]]) -> str:
    pattern = re.compile(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)", re.IGNORECASE)
    for label, text in sections:
        if pattern.search(text):
            return label
    return ""


def _comma_lists(text: str) -> list[tuple[str, int]]:
    found = []
    cursor = 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\n")
        if body.count(",") >= 2:
            parts = []
            for piece in re.split(r",|\band\b", body, flags=re.IGNORECASE):
                piece = re.sub(r"^[\s\-*•\d.)]+", "", piece)
                if ":" in piece:
                    piece = piece.split(":")[-1]
                piece = _clean_phrase(piece)
                words = piece.split()
                if piece and 1 <= len(words) <= 4 and not _all_stopwords(piece):
                    parts.append(piece)
            if len(parts) >= 3:
                offset = 0
                for phrase in parts:
                    at = body.lower().find(phrase.lower(), offset)
                    found.append((phrase, cursor + (at if at >= 0 else 0)))
                    if at >= 0:
                        offset = at + len(phrase)
        cursor += len(line)
    return found


def _repeated_phrases(text: str) -> list[tuple[str, int, int]]:
    counts: dict[tuple[str, ...], dict] = {}
    cursor = 0
    for chunk in re.split(r"([\n.!?]+)", text):
        if re.fullmatch(r"[\n.!?]+", chunk or ""):
            cursor += len(chunk)
            continue
        words = [(match.group(0), cursor + match.start()) for match in WORD.finditer(chunk)]
        for size in (1, 2, 3):
            for index in range(len(words) - size + 1):
                window = words[index : index + size]
                lowered = tuple(token.lower() for token, _position in window)
                if all(token in STOPWORDS for token in lowered):
                    continue
                if size == 1 and (lowered[0] in STOPWORDS or len(lowered[0]) < 4):
                    continue
                surface = " ".join(token for token, _position in window)
                slot = counts.setdefault(
                    lowered,
                    {"count": 0, "position": window[0][1], "surface": surface},
                )
                slot["count"] += 1
                if window[0][1] < slot["position"]:
                    slot["position"] = window[0][1]
                    slot["surface"] = surface
        cursor += len(chunk)
    repeated = [
        (slot["surface"], slot["position"], slot["count"])
        for slot in counts.values()
        if slot["count"] >= 2
    ]
    repeated.sort(key=lambda item: (-item[2], item[1]))
    return repeated[:25]


def _covers(longer: tuple[str, ...], shorter: tuple[str, ...]) -> bool:
    if len(shorter) >= len(longer):
        return False
    width = len(shorter)
    return any(longer[index : index + width] == shorter for index in range(len(longer) - width + 1))


def _tokens(keyword: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", keyword.lower()))


def _all_stopwords(phrase: str) -> bool:
    words = [re.sub(r"[^a-z0-9]+", "", word.lower()) for word in phrase.split()]
    words = [word for word in words if word]
    return bool(words) and all(word in STOPWORDS for word in words)


def _clean_phrase(phrase: str) -> str:
    return re.sub(r"\s+", " ", phrase).strip(" \t.,;:()[]{}")


def _is_acronym(token: str) -> bool:
    letters = re.sub(r"[^A-Za-z]", "", token)
    return len(letters) >= 2 and letters.isupper()


def _sentence_start(text: str, start: int) -> bool:
    prefix = text[:start].rstrip()
    return not prefix or prefix[-1] in ".!?\n"


def _line_is_term(text: str, start: int, end: int) -> bool:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    line = text[line_start:line_end].strip(" \t-*•")
    return line == text[start:end]


def _casing_score(value: str) -> int:
    return sum(1 for char in value if char.isupper())


def _text(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


REQUIRED_HEADING = re.compile(
    r"^(?:required qualifications|basic qualifications|minimum qualifications|minimum requirements|you will have(?:\s*/\s*required(?:\s+qualifications)?)?)$",
    re.IGNORECASE,
)
REQUIRED_EDUCATION_HEADING = re.compile(
    r"^(?:required education|minimum education|basic education)$",
    re.IGNORECASE,
)
PREFERRED_HEADING = re.compile(
    r"^(?:preferred\s+(?:qualifications|requirements|skills|experience)|nice to have|nice-to-have|skills\s+(?:&|and)\s+experience)$",
    re.IGNORECASE,
)
PREFERRED_EDUCATION_HEADING = re.compile(r"^preferred education$", re.IGNORECASE)
DEGREE_LEVELS = (
    (5, re.compile(r"\b(?:ph\.?d\.?|doctorate|doctoral)\b", re.IGNORECASE)),
    (4, re.compile(r"\b(?:mba|m\.b\.a\.?|master(?:'s|s)|master of|m\.s\.?|m\.a\.?)\b", re.IGNORECASE)),
    (3, re.compile(r"\b(?:bachelor(?:'s|s)?|bachelor of|b\.s\.?|b\.a\.?|undergraduate degree)\b", re.IGNORECASE)),
    (2, re.compile(r"\b(?:associate(?:'s|s)|associate degree|a\.a\.?|a\.s\.?)\b", re.IGNORECASE)),
    (1, re.compile(r"\b(?:high school|ged|secondary school)\b", re.IGNORECASE)),
)
DEGREE_LABELS = {
    1: "High school",
    2: "Associate degree",
    3: "Bachelor's degree",
    4: "Master's degree",
    5: "Doctorate",
}
SALARY_RE = re.compile(
    r"(\$\s?\d{1,3}(?:,\d{3})+(?:\.\d{2})?(?:\s*(?:-|–|—|to)\s*\$?\s?\d{1,3}(?:,\d{3})+(?:\.\d{2})?)?(?:\s*(?:per|/)\s*(?:year|hour|annum))?)",
    re.IGNORECASE,
)
LOCATION_LINE = re.compile(r"(?im)^(?:work location|job location|location)\s*:\s*(.+)$")
HIRING_PLACE = re.compile(
    r"\b(?:position|role)\s+in\s+([A-Z][^$\n]{2,80}?)\s+is\s+\$",
)
LOCATED_IN = re.compile(r"\blocated in\s+([A-Z][^.\n]{2,80})")
SECTION_END = re.compile(
    r"^(?:responsibilities|about the role(?:\s*(?:&|and)\s*team)?|about the team|job summary|what you(?:'|’)ll do|what you will do|education|benefits|overview)$",
    re.IGNORECASE,
)
REQUIREMENT_CUE = re.compile(
    r"(?:experience\s+(?:with|using|in)|familiarity\s+with|proficien(?:cy|t)\s+(?:in|with)|tools\s+such\s+as|such\s+as|e\.g\.|including)(?:\s*[:,]\s*|\s+)",
    re.IGNORECASE,
)
TOOL_TOKEN = re.compile(
    r"\b(?:[A-Za-z]{2,}(?:/[A-Za-z0-9]{2,})+|A/B|[A-Z]{2,}|[A-Z][a-z0-9]*[A-Z][A-Za-z0-9]*)\b"
)
GENERIC_WORDS = {
    "tools", "tool", "platforms", "platform", "language", "technologies",
    "technology", "software", "development", "methodology", "environments",
    "environment", "coding", "practices", "practice", "systems", "system",
    "particularly", "especially", "familiarity", "proficiency", "proficient",
    "preferably", "specifically", "following", "emerging", "query", "relevant",
}
MAX_REQUIREMENT_KEYWORDS = 12


def parse_requirements(text: str) -> dict:
    """Split a posting into required and preferred qualification rows."""
    required, preferred = _headed_requirements(text or "")
    if not required and not preferred:
        required = _fallback_requirements(text or "")
    return {"required": required, "preferred": preferred}


def analyze_requirements(description: str, review: dict | None = None) -> dict:
    """Return qualification keywords without comparing them to a resume."""
    parsed = parse_requirements(description or "")
    rows = apply_review([*parsed["required"], *parsed["preferred"]], review or {})
    required_rows = []
    preferred_rows = []
    for row in rows:
        item = {
            "text": row["text"],
            "kind": row.get("kind") or "skill",
            "label": row.get("label") or "",
            "keywords": list(row.get("keywords") or []),
        }
        if row["group"] == "preferred":
            preferred_rows.append(item)
        else:
            required_rows.append(item)
    return {"required": required_rows, "preferred": preferred_rows}


def match_qualifications(description: str, resume: dict, bullets: list | None = None, review: dict | None = None) -> dict:
    """Mark each qualification matched when every keyword is on the resume or a bullet tag."""
    parsed = parse_requirements(description or "")
    facts = extract_facts(description or "")
    review = review or {}
    rows = apply_review([*parsed["required"], *parsed["preferred"]], review)
    sections = _section_texts(resume or {})
    education = [item for item in (resume or {}).get("education") or [] if isinstance(item, dict)]
    accepted = {_norm(item) for item in review.get("matched") or []}
    placed = bullets or []
    skill_groups = _skill_candidates(resume or {})
    required_rows = []
    preferred_rows = []
    for row in rows:
        evaluated = _evaluate_requirement(row, sections, placed, education, accepted, skill_groups)
        if row["group"] == "preferred":
            preferred_rows.append(evaluated)
        else:
            required_rows.append(evaluated)
    return {
        "required_count": len(required_rows),
        "required_matched": sum(1 for row in required_rows if row["matched"]),
        "preferred_count": len(preferred_rows),
        "preferred_matched": sum(1 for row in preferred_rows if row["matched"]),
        "required": required_rows,
        "preferred": preferred_rows,
        "salary": facts["salary"],
        "locations": facts["locations"],
    }


def extract_facts(text: str) -> dict:
    """Pull a hiring range and work locations out of a posting."""
    salary = ""
    found = SALARY_RE.search(text or "")
    if found:
        salary = re.sub(r"\s+", " ", found.group(1)).strip()
    locations: list[str] = []
    seen: set[str] = set()
    for pattern in (LOCATION_LINE, HIRING_PLACE, LOCATED_IN):
        for match in pattern.finditer(text or ""):
            place = re.sub(r"\s+", " ", match.group(1)).strip(" .,;:-")
            key = place.lower()
            if not place or len(place) > 80 or key in seen:
                continue
            seen.add(key)
            locations.append(place)
    return {"salary": salary, "locations": locations}


def apply_review(rows: list[dict], review: dict) -> list[dict]:
    dismissed = {_norm(item) for item in review.get("dismissed") or []}
    kept = [row for row in rows if _norm(row["text"]) not in dismissed]
    seen = {_norm(row["text"]) for row in kept}
    for added in review.get("added") or []:
        text = _clean_phrase(_text(added.get("text")))
        if not text or _norm(text) in dismissed or _norm(text) in seen:
            continue
        group = "preferred" if added.get("group") == "preferred" else "required"
        kept.append(_requirement(text, group))
        seen.add(_norm(text))
    return kept


def _headed_requirements(text: str) -> tuple[list[dict], list[dict]]:
    required, preferred = [], []
    group = None
    for raw in text.splitlines():
        heading = _heading_group(raw)
        if heading == "end":
            group = None
            continue
        if isinstance(heading, tuple):
            group = heading
            continue
        if group is None:
            continue
        line = _clean_requirement_line(raw)
        if not line:
            continue
        if len(line.split()) > 45 or _is_pay_line(line):
            group = None
            continue
        if _is_location_line(line):
            continue
        requirement_group, kind = group
        if _is_degree_line(line):
            kind = "education"
        elif len(line.split()) < 3:
            continue
        bucket = required if requirement_group == "required" else preferred
        bucket.append(_requirement(line, requirement_group, kind))
    return required, preferred


def _fallback_requirements(text: str) -> list[dict]:
    rows = []
    seen = set()
    for chunk in re.split(r"[\n]+|(?<=[.])\s+", text):
        line = _clean_requirement_line(chunk)
        if not line or not REQUIREMENT_CUE.search(line):
            continue
        key = _norm(line)
        if key in seen:
            continue
        seen.add(key)
        rows.append(_requirement(line, "required"))
    return rows


def _requirement(text: str, group: str, kind: str = "skill") -> dict:
    if kind == "education" or _is_degree_line(text):
        label = _degree_label(text)
        return {
            "text": text,
            "group": group,
            "kind": "education",
            "label": label,
            "keywords": [label] if label else [],
        }
    return {
        "text": text,
        "group": group,
        "kind": "skill",
        "label": _short_label(text),
        "keywords": keywords_from_requirement(text),
    }


def keywords_from_requirement(text: str) -> list[str]:
    found: list[str] = []
    for match in REQUIREMENT_CUE.finditer(text):
        clause = re.split(r"(?<=\w)\.(?=\s|$)|[;\n]", text[match.end():], maxsplit=1)[0]
        for piece in re.split(r",|\bor\b|\band\b", clause, flags=re.IGNORECASE):
            kept = _keep_piece(piece)
            if kept:
                found.append(kept)
            else:
                found.extend(_tool_tokens(piece))
    if not REQUIREMENT_CUE.search(text):
        found.extend(_list_pieces(text))
    found.extend(_tool_tokens(text))
    chosen = _dedupe_keywords(found)
    if not chosen:
        words = text.split()
        tokens = [re.sub(r"[^a-z0-9/+#]+", "", word.lower()) for word in words]
        if (
            1 <= len(words) <= 3
            and tokens
            and all(token and token not in STOPWORDS and token not in GENERIC_WORDS for token in tokens)
        ):
            chosen = [_clean_phrase(text)]
    return chosen[:MAX_REQUIREMENT_KEYWORDS]


def _evaluate_requirement(row: dict, sections: list[tuple[str, str]], bullets: list, education: list, accepted: set, skill_groups: list | None = None) -> dict:
    manual = _norm(row["text"]) in accepted
    if row.get("kind") == "education":
        satisfied, detail = _education_match(row["text"], education)
        label = row.get("label") or _degree_label(row["text"])
        keywords = [
            {"keyword": label, "found": satisfied, "where": "Education" if satisfied else ""}
        ] if label else []
        return {
            "text": row["text"],
            "group": row["group"],
            "kind": "education",
            "label": label,
            "matched": satisfied or manual,
            "manual": manual,
            "detail": detail if satisfied else "This resume does not list a qualifying degree.",
            "keywords": keywords,
            "suggestions": [],
        }
    keywords = []
    suggestions = []
    for keyword in row["keywords"]:
        found, where = _keyword_found(keyword, sections, bullets)
        keywords.append({"keyword": keyword, "found": found, "where": where})
        if not found:
            suggestions.extend(_placement_options(keyword, row["text"], bullets, skill_groups or []))
    matched = bool(keywords) and all(item["found"] for item in keywords)
    return {
        "text": row["text"],
        "group": row["group"],
        "kind": "skill",
        "label": row.get("label") or _short_label(row["text"]),
        "matched": matched or manual,
        "manual": manual,
        "detail": "",
        "keywords": keywords,
        "suggestions": [] if matched or manual else suggestions,
    }


def _keyword_found(keyword: str, sections: list[tuple[str, str]], bullets: list) -> tuple[bool, str]:
    pattern = _keyword_pattern(keyword)
    for label, text in sections:
        if pattern.search(text):
            return True, label
    key = _norm(keyword)
    for bullet in bullets:
        if any(_norm(tag) == key for tag in bullet.get("tags") or []):
            return True, "tag"
        if pattern.search(_text(bullet.get("wording"))):
            return True, bullet.get("section") or "bullet"
    return False, ""


OVERLAP_WEIGHT = 10
RELATED_WEIGHT = 4
SECTION_WEIGHT = {
    "Work Experience": 2,
    "Projects": 2,
    "Leadership": 1,
    "Skills": 1,
}


def _skill_candidates(resume: dict) -> list[dict]:
    candidates = []
    for index, group in enumerate(resume.get("tool_groups") or []):
        if not isinstance(group, dict):
            continue
        name = _text(group.get("name"))
        items = [_text(item) for item in group.get("items") or []]
        notes = [_text(item) for item in group.get("bullets") or []]
        text = " ".join(part for part in (name, *items, *notes) if part)
        if not text.strip():
            continue
        candidates.append(
            {
                "kind": "skill_group",
                "bullet_id": None,
                "line_id": f"tool-group-{index}",
                "section": "Skills",
                "name": name or "Skills",
                "text": text,
                "excerpt": (name or ", ".join(item for item in items if item))[:140],
            }
        )
    return candidates


def _bullet_candidates(bullets: list) -> list[dict]:
    candidates = []
    for bullet in bullets:
        tags = [_text(tag) for tag in bullet.get("tags") or []]
        wording = _text(bullet.get("wording")).strip()
        parent = bullet.get("parent_id")
        index = bullet.get("line_index")
        line_id = f"{parent}-bullet-{index}" if parent not in (None, "") and index is not None else ""
        candidates.append(
            {
                "kind": "bullet",
                "bullet_id": str(bullet.get("id")) if bullet.get("id") else None,
                "line_id": line_id,
                "section": bullet.get("section") or "",
                "name": "",
                "text": " ".join(part for part in (wording, *tags) if part),
                "excerpt": wording[:140],
            }
        )
    return candidates


def _placement_reason(keyword: str, candidate: dict, overlap: set[str], related: str | None, combo: str | None) -> str:
    if candidate["kind"] == "bullet":
        reason = f'Add the tag "{keyword}" to this bullet only where it is true.'
        if overlap:
            return reason
        if related:
            return f"{reason} This line already mentions {related}, which is related to {keyword}."
        if combo:
            return f"{reason} This line mentions {combo}, which relates to {keyword}."
        return reason
    name = candidate["name"] or "Skills"
    if related:
        return f'Add "{keyword}" with {name}. This group already lists {related}, which is related to {keyword}.'
    if combo:
        return f'Add "{keyword}" with {name}. This group lists {combo}, which relates to {keyword}.'
    return f'Add "{keyword}" with {name} if you use it.'


def _skills_fallback(keyword: str) -> dict:
    return {
        "keyword": keyword,
        "bullet_id": None,
        "bullet_excerpt": "",
        "section": "Skills",
        "suggestion": f'Add "{keyword}" to Skills if you use it.',
        "line_id": "tools",
    }


def _placement_options(keyword: str, requirement: str, bullets: list, skill_groups: list) -> list[dict]:
    wanted = set(_content_tokens(requirement)) - set(_tokens(keyword))
    ranked = []
    for index, candidate in enumerate([*_bullet_candidates(bullets), *skill_groups]):
        overlap = wanted & set(_content_tokens(candidate["text"]))
        related = related_mention(keyword, candidate["text"])
        combo = None if related else combination_mention(keyword, candidate["text"])
        link = related or combo
        evidence = len(overlap) * OVERLAP_WEIGHT + (RELATED_WEIGHT if link else 0)
        if evidence <= 0:
            continue
        score = evidence + SECTION_WEIGHT.get(candidate["section"], 0)
        ranked.append((score, index, candidate, overlap, related, combo))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    options = []
    for _score, _index, candidate, overlap, related, combo in ranked[:2]:
        options.append(
            {
                "keyword": keyword,
                "bullet_id": candidate["bullet_id"],
                "bullet_excerpt": candidate["excerpt"],
                "section": candidate["section"],
                "suggestion": _placement_reason(keyword, candidate, overlap, related, combo),
                "line_id": candidate["line_id"],
            }
        )
    if not options:
        return [_skills_fallback(keyword)]
    if len(options) < 2:
        options.append(_skills_fallback(keyword))
    return options


def _heading_group(raw: str):
    cleaned = _clean_requirement_line(raw).strip(" :")
    if not cleaned or len(cleaned) > 80:
        return None
    if PREFERRED_EDUCATION_HEADING.match(cleaned):
        return ("preferred", "education")
    if REQUIRED_EDUCATION_HEADING.match(cleaned):
        return ("required", "education")
    if PREFERRED_HEADING.match(cleaned):
        return ("preferred", "skill")
    if REQUIRED_HEADING.match(cleaned):
        return ("required", "skill")
    if SECTION_END.match(cleaned):
        return "end"
    return None


def _is_pay_line(line: str) -> bool:
    lower = line.lower()
    return "per year" in lower or "per hour" in lower or "hiring range" in lower or bool(re.search(r"\$\s?\d", line))


def _is_location_line(line: str) -> bool:
    return bool(re.match(r"(?:work location|job location|location)\s*:", line, re.IGNORECASE))


def _is_degree_line(text: str) -> bool:
    return _required_level(text) is not None


def _degree_levels(text: str) -> list[int]:
    return [level for level, pattern in DEGREE_LEVELS if pattern.search(text or "")]


def _required_level(text: str) -> int | None:
    levels = _degree_levels(text)
    return min(levels) if levels else None


def _attained_level(text: str) -> int | None:
    levels = _degree_levels(text)
    return max(levels) if levels else None


def _degree_fields(text: str) -> list[str]:
    match = re.search(r"\b(?:degree|diploma)\s+in\s+(.+)", text or "", re.IGNORECASE)
    if not match:
        return []
    rest = re.split(
        r"\b(?:or\s+(?:an?\s+)?equivalent|or\s+(?:an?\s+)?related|related\s+field)\b|[.;]",
        match.group(1),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    fields = []
    for piece in re.split(r",|\bor\b|\band\b", rest, flags=re.IGNORECASE):
        cleaned = re.sub(r"\s+", " ", piece).strip(" .")
        tokens = [re.sub(r"[^a-z]+", "", word.lower()) for word in cleaned.split()]
        if not cleaned or all(
            token in {"a", "an", "the", "related", "field", "equivalent", "experience", "preferred", "required"} or not token
            for token in tokens
        ):
            continue
        fields.append(cleaned)
    return fields


def _degree_label(text: str) -> str:
    level = _required_level(text)
    if level is None:
        return _short_label(text)
    label = DEGREE_LABELS[level]
    fields = _degree_fields(text)
    if len(fields) == 1:
        return f"{label} in {fields[0]}"
    return label


def _field_required(text: str) -> bool:
    return bool(_degree_fields(text)) and not re.search(r"related\s+field|\bequivalent\b", text or "", re.IGNORECASE)


def _education_text(item: dict) -> str:
    return " ".join(
        _text(item.get(field))
        for field in ("degree", "degree_type", "degree_major", "institution")
    )


def _education_match(requirement: str, education: list) -> tuple[bool, str]:
    level = _required_level(requirement)
    if level is None:
        return False, ""
    fields = _degree_fields(requirement) if _field_required(requirement) else []
    for item in education:
        text = _education_text(item)
        attained = _attained_level(text)
        if attained is None or attained < level:
            continue
        if fields and not any(re.search(r"(?<!\w)" + re.escape(field) + r"(?!\w)", text, re.IGNORECASE) for field in fields):
            continue
        degree = _text(item.get("degree")) or _text(item.get("degree_type"))
        major = _text(item.get("degree_major"))
        if major and major.lower() not in degree.lower():
            degree = f"{degree}, {major}".strip(", ")
        institution = _text(item.get("institution"))
        return True, ", ".join(part for part in (degree, institution) if part)
    return False, ""


def _short_label(text: str) -> str:
    match = re.search(r"\bexperience\s+(?:in|with|using)\s+(.+)", text or "", re.IGNORECASE)
    clause = match.group(1) if match else text or ""
    clause = re.split(r"[.;]", clause, maxsplit=1)[0].strip()
    words = clause.split() or (text or "").split()
    label = " ".join(words[:8]).strip(" ,;:-")
    if len(words) > 8 and label:
        label += "…"
    return label or (text or "")


def _clean_requirement_line(raw: str) -> str:
    line = re.sub(r"^[\s\-*•]+", "", _text(raw))
    line = re.sub(r"^\d+[.)]\s*", "", line)
    return re.sub(r"\s+", " ", line).strip()


def _keep_piece(piece: str) -> str:
    cleaned = _clean_phrase(piece)
    cleaned = re.sub(
        r"^(?:particularly|especially|preferably|specifically|following|emerging|using|other)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    words = []
    for word in cleaned.split():
        token = re.sub(r"[^a-z0-9/+#]+", "", word.lower())
        generic = token in GENERIC_WORDS and not word[:1].isupper()
        if token in {"eg", "ie"} or token in STOPWORDS or generic:
            if words:
                break
            continue
        words.append(word.strip(".,;:()[]{}"))
    if not words or len(words) > 3:
        return ""
    if words[0].lower().endswith("ing") and not _is_tool_word(words[0]):
        return ""
    phrase = " ".join(words)
    tools = _tool_tokens(phrase)
    if any(_norm(tool) != _norm(phrase) for tool in tools):
        extras = [
            word
            for word in phrase.split()
            if not any(_norm(word) == _norm(tool) or _norm(tool) in _norm(word) or _norm(word) in _norm(tool) for tool in tools)
        ]
        if (
            extras
            and len(phrase.split()) <= 3
            and all(
                re.sub(r"[^a-z0-9]+", "", word.lower()) not in STOPWORDS
                and re.sub(r"[^a-z0-9]+", "", word.lower()) not in GENERIC_WORDS
                for word in extras
            )
        ):
            return phrase
        return ""
    return phrase


def _list_pieces(text: str) -> list[str]:
    if text.count(",") < 1 and not re.search(r"\b(?:and|or)\b", text, re.IGNORECASE):
        return []
    kept = []
    for piece in re.split(r",|\band\b|\bor\b", text, flags=re.IGNORECASE):
        item = _keep_piece(piece)
        if not item or len(item.split()) > 2:
            return []
        kept.append(item)
    if len(kept) < 2:
        return []
    if not any(word[:1].isupper() or _is_tool_word(word) for item in kept for word in item.split()):
        return []
    return kept


def _tool_tokens(text: str) -> list[str]:
    found = []
    for match in TOOL_TOKEN.finditer(text or ""):
        token = match.group(0).strip(".,;:")
        parts = [part for part in re.split(r"[/]", token) if part]
        if _all_stopwords(token) or token.upper() in ACRONYM_SKIP:
            continue
        if parts and all(part.lower() in STOPWORDS or part.lower() in GENERIC_WORDS for part in parts):
            continue
        letters = re.sub(r"[^A-Za-z]", "", token)
        if letters.isupper() or _is_camel(token) or "/" in token or token == "A/B":
            found.append(token)
    return found


def _is_tool_word(word: str) -> bool:
    letters = re.sub(r"[^A-Za-z]", "", word)
    return bool(letters) and (letters.isupper() or _is_camel(word) or "/" in word)


def _is_camel(token: str) -> bool:
    return bool(re.search(r"[A-Z].*[A-Z]", token)) and not token.isupper()


def _dedupe_keywords(keywords: list[str]) -> list[str]:
    chosen: list[str] = []
    chosen_tokens: list[tuple[str, ...]] = []
    for keyword in keywords:
        cleaned = _clean_phrase(keyword)
        if not cleaned or _all_stopwords(cleaned):
            continue
        tokens = _tokens(cleaned)
        if not tokens:
            continue
        if any(tokens == existing or _covers(existing, tokens) for existing in chosen_tokens):
            continue
        replaced = False
        for index, existing in enumerate(chosen_tokens):
            if _covers(tokens, existing):
                chosen[index] = cleaned
                chosen_tokens[index] = tokens
                replaced = True
                break
        if not replaced:
            chosen.append(cleaned)
            chosen_tokens.append(tokens)
    return chosen


def _keyword_pattern(keyword: str) -> re.Pattern:
    return re.compile(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)", re.IGNORECASE)


def _content_tokens(text: str) -> list[str]:
    return [token for token in _tokens(text) if token not in STOPWORDS and token not in GENERIC_WORDS]


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", _text(value)).strip().lower()
