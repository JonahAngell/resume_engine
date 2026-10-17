"""Compare job-description keywords with the text of a saved resume."""

import re
from dataclasses import dataclass
from datetime import date

from .keywords import *

from .related_skills import (
    category_for_term,
    clusters_in_text,
    combination_mention,
    covers_token,
    find_terms,
    is_known_term,
    job_families,
    mentions,
    related_mention,
)

MAX_KEYWORDS = 40

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
    category = category_for_term(keyword)
    if category:
        return category
    if _soft_skill_labels(keyword):
        return "soft_skill"
    if _credential_labels(keyword):
        return "credential"
    if _is_degree_line(keyword):
        return "degree"
    return "tool"


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
    r"^(?:required qualifications|basic qualifications|minimum qualifications|minimum requirements|you will have)$",
    re.IGNORECASE,
)
REQUIRED_EDUCATION_HEADING = re.compile(
    r"^(?:required education|minimum education|basic education)$",
    re.IGNORECASE,
)
PREFERRED_HEADING = re.compile(
    r"^(?:preferred(?:\s+(?:qualifications|requirements|skills|experience))?|nice to have|nice-to-have|skills\s+(?:&|and)\s+experience|preferences)$",
    re.IGNORECASE,
)
PREFERRED_EDUCATION_HEADING = re.compile(r"^preferred education$", re.IGNORECASE)
BARE_EDUCATION_HEADING = re.compile(r"^education$", re.IGNORECASE)
DEGREE_LEVELS = (
    (5, re.compile(r"\b(?:ph\.?d\.?|doctorate|doctoral)\b", re.IGNORECASE)),
    (4, re.compile(r"\b(?:mba|m\.b\.a\.?|master(?:'s|s)|master of|m\.s\.?|m\.a\.?)\b", re.IGNORECASE)),
    (3, re.compile(r"\b(?:bachelor(?:'s|s)?|bachelor of|b\.s\.?|b\.a\.?|undergraduate degree)\b", re.IGNORECASE)),
    (2, re.compile(r"\b(?:associate(?:'s|s)|associate degree|a\.a\.?|a\.s\.?)\b", re.IGNORECASE)),
    (1, re.compile(r"\b(?:high school|ged|secondary school)\b", re.IGNORECASE)),
)

SALARY_RE = re.compile(
    r"(\$\s?\d{1,3}(?:,\d{3})+(?:\.\d{2})?(?:\s*(?:-|–|—|to)\s*\$?\s?\d{1,3}(?:,\d{3})+(?:\.\d{2})?)?(?:\s*(?:per|/)\s*(?:year|hour|annum))?)",
    re.IGNORECASE,
)
LOCATION_LINE = re.compile(r"(?im)^(?:work location|job location|location)\s*:\s*(.+)$")
HIRING_PLACE = re.compile(
    r"\b(?:position|role)\s+in\s+([A-Z][^$\n]{2,80}?)\s+is\s+\$",
)
LOCATED_IN = re.compile(r"\blocated in\s+([A-Z][^.\n]{2,80})")
RESPONSIBILITY_HEADING = re.compile(
    r"^(?:responsibilities(?:\s+and\s+duties(?:\s+of\s+the\s+role)?)?(?:\s*/\s*you will(?:\s+have)?)?|key responsibilities|what you(?:'|’)ll do|what you will do|about the role(?:\s*(?:&|and)\s*(?:the )?(?:team|program))?|the role)$",
    re.IGNORECASE,
)
BOILERPLATE_HEADING = re.compile(
    r"^(?:benefits(?:\s*(?:&|and)\s*perks)?|overview|additional information|disclaimer|about the team|job summary|the team|the opportunity)$",
    re.IGNORECASE,
)
SCHEDULE_HEADING = re.compile(
    r"^(?:schedule|work schedule|hours|location|work location|job location|travel|employment type|position type)$",
    re.IGNORECASE,
)
SECTION_WEIGHTS = {
    "required": 1.0,
    "preferred": 0.45,
    "responsibility": 0.65,
    "boilerplate": 0.0,
}
EVIDENCE_STRENGTH = {
    "exact": 1.0,
    "alias": 0.9,
    "cluster": 0.55,
    "combination": 0.45,
    "semantic": 0.0,
}
GATE_CATEGORIES = {"degree", "experience_duration", "credential"}
RELEVANCE_CATEGORIES = {"tool", "domain", "responsibility", "methodology", "soft_skill"}
NEGATED_LINE = re.compile(
    r"\b(?:no experience required|experience not required|not required|willing to learn|willingness to learn|no prior experience)\b",
    re.IGNORECASE,
)
SOFT_SKILLS = (
    ("communication", re.compile(r"\bcommunications?\b", re.IGNORECASE)),
    ("problem-solving", re.compile(r"\bproblem[- ]solving\b", re.IGNORECASE)),
    ("attention to detail", re.compile(r"\battention to detail\b", re.IGNORECASE)),
    ("time management", re.compile(r"\btime management\b", re.IGNORECASE)),
    ("interpersonal", re.compile(r"\binterpersonal\b", re.IGNORECASE)),
    ("self-starter", re.compile(r"\bself[- ]starter\b", re.IGNORECASE)),
    ("organizational", re.compile(r"\borganizational skills\b", re.IGNORECASE)),
)
CREDENTIALS = (
    ("CPA", re.compile(r"\bCPAs?\b")),
    ("PMP", re.compile(r"\bPMPs?\b")),
    ("CFA", re.compile(r"\bCFAs?\b")),
    ("CMA", re.compile(r"\bCMAs?\b")),
    ("Certification", re.compile(r"\bcertifications?\b", re.IGNORECASE)),
    ("Certificate", re.compile(r"\bcertificates?\b", re.IGNORECASE)),
    ("License", re.compile(r"\blicen[sc]es?\b", re.IGNORECASE)),
)
YEAR_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
SCHEDULE_CUE = re.compile(r"\b(full[- ]time|part[- ]time|night shifts?|shift work|weekends)\b", re.IGNORECASE)
TRAVEL_CUE = re.compile(r"\b(\d+\s*%\s*travel|travel(?:\s+up)?(?:\s+to)?\s+\d+\s*%)\b", re.IGNORECASE)
EMPLOYMENT_CUE = re.compile(r"\b(contract|permanent|temporary|hourly|internship)\b", re.IGNORECASE)
WORK_MODE_CUE = re.compile(r"\b(remote|hybrid|on[- ]site|onsite)\b", re.IGNORECASE)
STRONG_LINE = re.compile(
    r"(?:experience\s+(?:with|using|in)|familiarity\s+(?:with|in)|proficien(?:cy|t)(?:\s+(?:in|with))?|knowledge\s+of|skilled\s+in)",
    re.IGNORECASE,
)
YEARS_LINE = re.compile(
    r"(?:\d+\s*\+\s*years|\d+\s*-\s*\d+\s*years|minimum(?:\s+of)?\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+years)",
    re.IGNORECASE,
)
EXAMPLE_CUE = re.compile(
    r"(?<!\w)(?:such\s+as|for\s+example|including|aka|ie|e\.g\.|i\.e\.)(?!\w)",
    re.IGNORECASE,
)



TOOL_TOKEN = re.compile(
    r"\b(?:[A-Za-z]{2,}(?:/[A-Za-z0-9]{2,})+|A/B|[A-Z]{2,}|[A-Z][a-z0-9]*[A-Z][A-Za-z0-9]*)\b"
)

MAX_REQUIREMENT_KEYWORDS = 12


def parse_requirements(text: str) -> dict:
    """Split a posting into relevance rows and eligibility gates."""
    return _route(_headed_requirements(text or ""))


def analyze_requirements(description: str, review: dict | None = None) -> dict:
    """Return qualification keywords without comparing them to a resume."""
    parsed = parse_requirements(description or "")
    rows = apply_review(_parsed_rows(parsed), review or {})
    routed = _route(rows)
    return {key: [_analysis_item(row) for row in routed[key]] for key in routed}


def match_qualifications(description: str, resume: dict, bullets: list | None = None, review: dict | None = None) -> dict:
    """Mark each qualification matched when its keyword rule is satisfied."""
    description = description or ""
    resume = resume or {}
    parsed = parse_requirements(description)
    facts = extract_facts(description)
    review = review or {}
    routed = _route(apply_review(_parsed_rows(parsed), review))
    families = classify_families(description)
    education = [item for item in resume.get("education") or [] if isinstance(item, dict)]
    accepted = {_norm(item) for item in review.get("matched") or []}
    placed = bullets or []
    skill_groups = _skill_candidates(resume)
    candidates = _match_candidates(resume, placed, skill_groups)
    evaluated = {
        key: [
            _evaluate_requirement(row, candidates, placed, education, accepted, skill_groups)
            for row in routed[key]
        ]
        for key in routed
    }
    required_rows = evaluated["required"]
    preferred_rows = evaluated["preferred"]
    return {
        "required_count": len(required_rows),
        "required_matched": sum(1 for row in required_rows if row["matched"]),
        "preferred_count": len(preferred_rows),
        "preferred_matched": sum(1 for row in preferred_rows if row["matched"]),
        "required": required_rows,
        "preferred": preferred_rows,
        "responsibilities": evaluated["responsibilities"],
        "eligibility_rows": evaluated["eligibility"],
        "salary": facts["salary"],
        "locations": facts["locations"],
        "scores": _score_components(evaluated, families, resume),
        "eligibility": _eligibility(evaluated["eligibility"], _parsed_rows(routed), resume, description, facts),
        "families": families,
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
        row = _requirement(text, group, "skill", group)
        if row is None:
            row = _blank_row(text, group, group, "responsibility", [], "all", [], _short_label(text))
        kept.append(row)
        seen.add(_norm(text))
    return kept


def _parsed_rows(parsed: dict) -> list[dict]:
    return [
        *(parsed.get("required") or []),
        *(parsed.get("preferred") or []),
        *(parsed.get("responsibilities") or []),
        *(parsed.get("eligibility") or []),
    ]


def _analysis_item(row: dict) -> dict:
    return {
        "text": row["text"],
        "kind": row.get("kind") or row.get("category") or "tool",
        "label": row.get("label") or "",
        "keywords": list(row.get("keywords") or []),
        "match_mode": row.get("match_mode") or "all",
        "category": row.get("category") or row.get("kind") or "",
        "section": row.get("section") or row.get("group") or "",
        "weight": float(row.get("weight") or 0),
    }


def _route(rows: list[dict]) -> dict:
    routed = {"required": [], "preferred": [], "responsibilities": [], "eligibility": []}
    for row in rows:
        if row.get("category") in GATE_CATEGORIES:
            routed["eligibility"].append(row)
            continue
        if float(row.get("weight") or 0) <= 0 or row.get("category") not in RELEVANCE_CATEGORIES:
            continue
        group = row.get("group")
        if group == "responsibility":
            routed["responsibilities"].append(row)
        elif group == "preferred":
            routed["preferred"].append(row)
        elif group == "required":
            routed["required"].append(row)
    return routed


def _headed_requirements(text: str) -> list[dict]:
    rows: list[dict] = []
    group = None
    seen: set[str] = set()

    def store(row: dict | None) -> None:
        if not row:
            return
        key = _norm(f"{row['text']}|{row.get('category')}")
        if key in seen:
            return
        seen.add(key)
        rows.append(row)

    def add(line: str, target_group: str, section: str) -> None:
        if _is_negated(line):
            return
        if section in {"responsibility", "outside", "boilerplate"} and _example_only(line):
            return
        if _is_degree_line(line) and _credential_labels(line):
            store(_degree_row(line, target_group, "education"))
            store(_credential_row(line, target_group, section))
            return
        hint = "education" if section == "education" else "skill"
        store(_requirement(line, target_group, hint, section))

    for raw in text.splitlines():
        heading = _heading_group(raw)
        if heading == "skip":
            group = "skip"
            continue
        if isinstance(heading, tuple):
            group = heading
            continue
        line = _clean_requirement_line(raw)
        if not line or _is_location_line(line):
            continue
        if len(line.split()) > 45 or _is_pay_line(line):
            group = None
            continue
        if group == "skip":
            continue
        if group is None:
            for chunk in _outside_chunks(line):
                if _is_pay_line(chunk) or len(chunk.split()) > 45 or not _strong_outside(chunk):
                    continue
                add(chunk, "required", "outside")
            continue
        target, hint = group
        if target == "inline":
            if not _is_degree_line(line):
                continue
            preferred_line = bool(re.search(r"\bpreferred\b", line, re.IGNORECASE)) and not re.search(
                r"\brequired\b", line, re.IGNORECASE
            )
            add(line, "preferred" if preferred_line else "required", "education")
            continue
        if hint == "education" and not _is_degree_line(line):
            continue
        add(line, target, "education" if hint == "education" else target)
    return rows


def _outside_chunks(line: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.])\s+", line) if part.strip()]


def _strong_outside(line: str) -> bool:
    if _is_negated(line):
        return False
    if _is_pure_degree(line) or _is_degree_line(line) or _credential_labels(line):
        return True
    if not (STRONG_LINE.search(line) or YEARS_LINE.search(line)):
        return False
    row = _requirement(line, "required", "skill", "outside")
    return row is not None


def _requirement(text: str, group: str, kind: str = "skill", section: str | None = None) -> dict | None:
    section = section or ("education" if kind == "education" else group)
    if _is_negated(text):
        return None
    if section in {"responsibility", "outside", "boilerplate"} and _example_only(text):
        return None
    if _is_pure_degree(text) or (kind == "education" and _is_degree_line(text)):
        return _degree_row(text, group, "education")
    if kind == "education":
        return None
    clauses = []
    for clause in _split_clauses(text):
        mode, keywords = _clause_spec(clause)
        if keywords:
            clauses.append({"mode": mode, "keywords": keywords})
    keywords = _dedupe_keywords([keyword for clause in clauses for keyword in clause["keywords"]])
    category = _line_category(text, keywords, "responsibility" if section == "responsibility" else section)
    if category == "degree":
        return _degree_row(text, group, "education")
    if category == "credential":
        return _credential_row(text, group, section, keywords)
    if category == "experience_duration":
        label = _short_label(text)
        return _blank_row(text, group, section, category, [label] if label else [], "all", [{"mode": "all", "keywords": [label] if label else []}], label)
    if category == "soft_skill":
        labels = _soft_skill_labels(text) or keywords
        return _blank_row(text, group, section, category, labels, "all", [{"mode": "all", "keywords": labels}], _short_label(text))
    if not keywords or category not in RELEVANCE_CATEGORIES:
        return None
    match_mode = "any" if len(clauses) == 1 and clauses[0]["mode"] == "any" else "all"
    return _blank_row(text, group, section, category, keywords, match_mode, clauses, _short_label(text))


def _blank_row(text: str, group: str, section: str, category: str, keywords: list[str], match_mode: str, clauses: list, label: str) -> dict:
    return {
        "text": text,
        "group": group,
        "section": section,
        "category": category,
        "kind": category,
        "label": label,
        "keywords": keywords,
        "match_mode": match_mode,
        "clauses": clauses or [{"mode": match_mode, "keywords": list(keywords)}],
        "weight": SECTION_WEIGHTS.get(group, SECTION_WEIGHTS["required"]),
        "years": _min_years(text),
    }


def _degree_row(text: str, group: str, section: str) -> dict:
    label = _degree_label(text)
    keywords = [label] if label else []
    return _blank_row(text, group, section, "degree", keywords, "all", [{"mode": "all", "keywords": keywords}], label)


def _credential_row(text: str, group: str, section: str, keywords: list[str] | None = None) -> dict:
    labels = _credential_labels(text) or list(keywords or [])
    mode = "any" if len(labels) > 1 else "all"
    return _blank_row(text, group, section, "credential", labels, mode, [{"mode": mode, "keywords": labels}], labels[0] if len(labels) == 1 else _short_label(text))


def _line_category(text: str, keywords: list[str], section: str) -> str:
    taxonomy = _taxonomy_categories(keywords)
    degree = _is_degree_line(text)
    credentials = _credential_labels(text)
    if degree and (not taxonomy or _is_pure_degree(text)):
        return "degree"
    if credentials and not taxonomy:
        return "credential"
    if _min_years(text) is not None and not taxonomy:
        return "experience_duration"
    soft = _soft_skill_labels(text)
    if soft and not taxonomy:
        return "soft_skill"
    if taxonomy:
        return _majority_category(taxonomy)
    if section == "responsibility":
        return "responsibility" if keywords else ""
    if soft:
        return "soft_skill"
    return ""


def _taxonomy_categories(keywords: list[str]) -> list[str]:
    categories = []
    for keyword in keywords:
        category = category_for_term(keyword)
        if category:
            categories.append(category)
    return categories


def _majority_category(categories: list[str]) -> str:
    counts: dict[str, int] = {}
    for category in categories:
        counts[category] = counts.get(category, 0) + 1
    best = max(counts.values())
    winners = [category for category, count in counts.items() if count == best]
    for preferred in ("tool", "domain", "methodology"):
        if preferred in winners:
            return preferred
    return winners[0]


def _soft_skill_labels(text: str) -> list[str]:
    return [label for label, pattern in SOFT_SKILLS if pattern.search(text or "")]


def _credential_labels(text: str) -> list[str]:
    return [label for label, pattern in CREDENTIALS if pattern.search(text or "")]


def _min_years(text: str) -> float | None:
    found = []
    pattern = re.compile(
        r"(\d+)\s*\+\s*years|\b(\d+)\s*-\s*\d+\s*years|minimum(?:\s+of)?\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+years",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text or ""):
        raw = next(group for group in match.groups() if group)
        found.append(float(YEAR_WORDS.get(raw.lower(), raw)))
    return min(found) if found else None


def _is_negated(text: str) -> bool:
    return bool(NEGATED_LINE.search(text or ""))


def _example_only(text: str) -> bool:
    match = EXAMPLE_CUE.search(text or "")
    if not match:
        return False
    before = text[: match.start()]
    return not before.strip() or not _extract_keywords(before)


def _is_pure_degree(text: str) -> bool:
    if not _is_degree_line(text):
        return False
    leftover = re.sub(r"\band/or\s+(?:an?\s+)?equivalent\b", "", text or "", flags=re.IGNORECASE)
    return not re.search(r"\band/or\b", leftover, re.IGNORECASE)


def _split_clauses(text: str) -> list[str]:
    pieces = re.split(r";\s*", text)
    chunks = pieces if len(pieces) > 1 and any(len(piece.split()) > 6 for piece in pieces) else [text]
    refined = []
    for chunk in chunks:
        refined.extend(
            re.split(
                r"\s+\band\s+(?=(?:experience|familiarity|proficiency|knowledge)\b)",
                chunk,
                flags=re.IGNORECASE,
            )
        )
    return [part.strip(" ,") for part in refined if part and part.strip(" ,")]


def _clause_spec(clause: str) -> tuple[str, list[str]]:
    keywords = _extract_keywords(clause)
    if len(keywords) > 1 and _is_any_clause(clause):
        return "any", keywords
    return "all", keywords


def _is_any_clause(clause: str) -> bool:
    if EXAMPLE_CUE.search(clause) or re.search(r"\band/or\b", clause, re.IGNORECASE):
        return True
    if _known_word_slash(clause) or _spaced_slash_keywords(clause):
        return True
    reduced = re.sub(r"\bor\s+(?:an?\s+)?(?:equivalent|related)\b", "", clause, flags=re.IGNORECASE)
    return bool(re.search(r"\bor\b", reduced, re.IGNORECASE))


def _known_word_slash(clause: str) -> bool:
    for match in re.finditer(
        r"\b([A-Za-z][A-Za-z0-9+#.]*)\s*/\s*([A-Za-z][A-Za-z0-9+#.]*)",
        clause,
    ):
        if is_known_term(match.group(1)) and is_known_term(match.group(2)):
            return True
    return False


def _spaced_slash_keywords(clause: str) -> bool:
    if not re.search(r"\s/\s", clause):
        return False
    parts = [part for part in re.split(r"\s/\s", clause) if part.strip()]
    return len(parts) >= 2 and all(_extract_keywords(part) for part in parts)


def keywords_from_requirement(text: str) -> list[str]:
    row = _requirement(text, "required")
    if not row:
        return []
    return list(row["keywords"])


def _extract_keywords(text: str) -> list[str]:
    regions = _keyword_regions(text)
    if regions != [text]:
        keywords = _dedupe_keywords(
            [keyword for region in regions for keyword in _terms_from_region(region, True)]
        )
        if keywords:
            return keywords
    return _dedupe_keywords(_terms_from_region(text, False))


def _keyword_regions(text: str) -> list[str]:
    matches = list(EXAMPLE_CUE.finditer(text))
    if not matches:
        return [text]
    regions = []
    first = matches[0].start()
    if matches[0].group(0).lower() == "aka":
        regions.append(text[max(0, first - 48) : first])
    else:
        for paren in re.finditer(r"\(([^)]*)\)", text[:first]):
            if not EXAMPLE_CUE.search(paren.group(1)):
                regions.append(paren.group(1))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        regions.append(text[match.end() : end])
    return [region for region in regions if region.strip()]


def _terms_from_region(text: str, from_cue: bool) -> list[str]:
    keywords: list[str] = []
    last = 0
    for match in re.finditer(r"\(([^)]*)\)", text):
        before = text[last : match.start()]
        inner_terms = _core_terms(match.group(1))
        before_terms = _core_terms(before)
        if len(inner_terms) >= 2 and before_terms and before_terms[-1].lower() in UMBRELLAS:
            before_terms = before_terms[:-1]
        keywords.extend(before_terms)
        keywords.extend(inner_terms)
        last = match.end()
    keywords.extend(_core_terms(text[last:]))
    keywords.extend(_list_only_terms(text))
    keywords.extend(_proper_list_items(text, from_cue))
    return [keyword for keyword in keywords if not re.search(
        re.escape(keyword) + r"\s+tools\b",
        text,
        flags=re.IGNORECASE,
    )]


def _core_terms(text: str) -> list[str]:
    found = list(find_terms(text))
    found.extend(_uncovered_tool_tokens(text, found))
    return _dedupe_keywords(found)


def _uncovered_tool_tokens(text: str, found: list[str]) -> list[str]:
    extras = []
    for match in TOOL_TOKEN.finditer(text or ""):
        token = match.group(0).strip(".,;:()")
        if not token or token.upper() in ACRONYM_SKIP or _token_covered(token, found):
            continue
        parts = [part for part in token.split("/") if part]
        if "/" in token and not any(char.isupper() for char in token):
            continue
        if len(parts) >= 2 and all(is_known_term(part) for part in parts):
            continue
        if "/" in token and all(
            part.lower() in STOPWORDS or part.lower() in GENERIC_WORDS or part.lower() in GENERIC_LIST
            for part in parts
        ):
            continue
        letters = re.sub(r"[^A-Za-z]", "", token)
        if _all_stopwords(token) or not letters:
            continue
        if letters.isupper() or _is_camel(token) or "/" in token:
            extras.append(token)
    return extras


def _token_covered(token: str, found: list[str]) -> bool:
    token_norm = tuple(re.findall(r"[a-z0-9]+", token.lower()))
    for display in found:
        if mentions(display, token) or mentions(token, display) or covers_token(display, token):
            return True
        display_norm = tuple(re.findall(r"[a-z0-9]+", display.lower()))
        if token_norm and (token_norm == display_norm or _covers(display_norm, token_norm)):
            return True
    return False


def _list_only_terms(text: str) -> list[str]:
    if text.count(",") < 1 and not re.search(r"\b(?:and|or)\b", text, re.IGNORECASE):
        return []
    extras = []
    for piece in re.split(r",|\band/or\b|\band\b|\bor\b", text, flags=re.IGNORECASE):
        words = re.findall(r"[A-Za-z][A-Za-z0-9+#]*", piece)
        if len(words) == 1 and words[0].lower() in LIST_ONLY:
            extras.append(LIST_ONLY[words[0].lower()])
            continue
        if (
            words
            and words[-1].lower() in LIST_ONLY
            and re.search(r"proficienc|experience\s+with|skilled\s+in", piece, re.IGNORECASE)
        ):
            extras.append(LIST_ONLY[words[-1].lower()])
    return extras


def _proper_list_items(text: str, from_cue: bool = False) -> list[str]:
    if text.count(",") < 1:
        return []
    if not from_cue and not re.search(
        r"(?:such\s+as|e\.g\.|i\.e\.|\bie\b|experience\s+with|familiarity\s+with|proficienc|tools)",
        text,
        re.IGNORECASE,
    ):
        return []
    extras = []
    for piece in re.split(r",|\band/or\b|\band\b|\bor\b", text, flags=re.IGNORECASE):
        piece = re.sub(r"\([^)]*\)", "", piece).strip(" .;:-")
        words = piece.split()
        if not 1 <= len(words) <= 3 or not all(word[:1].isupper() for word in words):
            continue
        alphas = [re.sub(r"[^a-z]", "", word.lower()) for word in words]
        if not alphas or any(not token or token in STOPWORDS or token in GENERIC_LIST for token in alphas):
            continue
        cleaned = _clean_phrase(piece)
        if cleaned:
            extras.append(cleaned)
    return extras


def _evaluate_requirement(row: dict, candidates: list, bullets: list, education: list, accepted: set, skill_groups: list | None = None) -> dict:
    manual = _norm(row["text"]) in accepted
    category = row.get("category") or row.get("kind") or "tool"
    if category == "degree" or row.get("kind") in {"education", "degree"}:
        satisfied, detail = _education_match(row["text"], education)
        label = row.get("label") or _degree_label(row["text"])
        evidence = None
        if satisfied and detail:
            evidence = {
                "source_requirement": row["text"],
                "matched_text": detail,
                "relation": "exact",
                "section": "Education",
                "confidence": EVIDENCE_STRENGTH["exact"],
                "explanation": "This resume lists a qualifying degree.",
            }
        keywords = [
            {
                "keyword": label,
                "found": satisfied,
                "where": "Education" if satisfied else "",
                "relation": "exact" if satisfied else "",
                "evidence": evidence,
            }
        ] if label else []
        return _public_row(
            row,
            "degree",
            label,
            "all",
            satisfied or manual,
            manual,
            detail if satisfied else "This resume does not list a qualifying degree.",
            keywords,
            [],
        )
    keywords = []
    pending = []
    for keyword in row["keywords"]:
        item = _keyword_payload(keyword, row["text"], candidates)
        keywords.append(item)
        if not item["found"]:
            pending.append(keyword)
    found_map = {item["keyword"]: item["found"] for item in keywords}
    clauses = row.get("clauses") or [{"mode": row.get("match_mode") or "all", "keywords": list(row["keywords"])}]
    matched = bool(keywords) and all(_clause_matched(clause, found_map) for clause in clauses)
    match_mode = row.get("match_mode") or "all"
    if matched or manual:
        suggestions = []
    elif match_mode == "any":
        suggestions = _any_suggestions(pending, row["text"], bullets, skill_groups or [])
    else:
        suggestions = []
        for keyword in pending:
            suggestions.extend(_placement_options(keyword, row["text"], bullets, skill_groups or []))
    suggestions = [_with_action(item, category) for item in suggestions]
    return _public_row(
        row,
        category,
        row.get("label") or _short_label(row["text"]),
        match_mode,
        matched or manual,
        manual,
        "",
        keywords,
        suggestions,
    )


def _public_row(row: dict, category: str, label: str, match_mode: str, matched: bool, manual: bool, detail: str, keywords: list, suggestions: list) -> dict:
    return {
        "text": row["text"],
        "group": row["group"],
        "section": row.get("section") or row.get("group") or "",
        "category": category,
        "kind": category,
        "label": label,
        "weight": float(row.get("weight") or 0),
        "match_mode": match_mode,
        "matched": matched,
        "manual": manual,
        "detail": detail,
        # skill: the keyword belongs in Skills, so the UI offers Add to Skills, not AI wording.
        "keywords": [{**item, "skill": is_skill_keyword(item.get("keyword") or "", category)} for item in keywords],
        "suggestions": suggestions,
    }


def _keyword_payload(keyword: str, requirement: str, candidates: list) -> dict:
    evidence = _best_evidence(keyword, requirement, candidates)
    relation = evidence["relation"] if evidence else ""
    found = relation in {"exact", "alias"}
    return {
        "keyword": keyword,
        "found": found,
        "where": evidence["section"] if found and evidence else "",
        "relation": relation,
        "evidence": evidence,
    }


def _best_evidence(keyword: str, requirement: str, candidates: list) -> dict | None:
    best = None
    for index, candidate in enumerate(candidates):
        relation, related, combo = _relation_on(keyword, candidate.get("text") or "")
        if not relation or EVIDENCE_STRENGTH.get(relation, 0) <= 0:
            continue
        rank = (EVIDENCE_STRENGTH[relation], SECTION_WEIGHT.get(candidate.get("section") or "", 0), -index)
        if best and rank <= best[0]:
            continue
        best = (
            rank,
            {
                "source_requirement": requirement,
                "matched_text": (candidate.get("excerpt") or candidate.get("text") or "")[:140],
                "relation": relation,
                "section": candidate.get("section") or "",
                "confidence": EVIDENCE_STRENGTH[relation],
                "explanation": _evidence_explanation(keyword, relation, related, combo),
            },
        )
    return best[1] if best else None


def _relation_on(keyword: str, text: str) -> tuple[str | None, str | None, str | None]:
    if _keyword_pattern(keyword).search(text or ""):
        return "exact", None, None
    if mentions(keyword, text) or _bare_tool_hit(keyword, text):
        return "alias", None, None
    related = related_mention(keyword, text)
    if related:
        return "cluster", related, None
    combo = combination_mention(keyword, text)
    if combo:
        return "combination", None, combo
    return None, None, None


def _evidence_explanation(keyword: str, relation: str, related: str | None, combo: str | None) -> str:
    if relation == "exact":
        return f'"{keyword}" appears in this text.'
    if relation == "alias":
        return f'This text uses another name for "{keyword}".'
    if relation == "cluster":
        return f'This text mentions {related}, which is in the same group as "{keyword}".'
    if relation == "combination":
        return f'This text mentions {combo}, which relates to "{keyword}".'
    return ""


def _match_candidates(resume: dict, bullets: list, skill_groups: list) -> list[dict]:
    candidates = []
    summary = _text(resume.get("summary")).strip()
    if summary:
        candidates.append({"section": "Summary", "text": summary, "excerpt": summary[:140]})
    candidates.extend(_bullet_candidates(bullets))
    for group in skill_groups:
        candidates.append(group)
    for group in resume.get("tool_groups") or []:
        if not isinstance(group, dict):
            continue
        for item in [*(group.get("items") or []), *(group.get("bullets") or [])]:
            text = _text(item).strip()
            if text:
                candidates.append({"section": "Skills", "text": text, "excerpt": text[:140]})
    for item in resume.get("education") or []:
        if not isinstance(item, dict):
            continue
        text = _education_text(item).strip()
        if text:
            candidates.append({"section": "Education", "text": text, "excerpt": text[:140]})
    if not bullets:
        for label, text in _section_texts(resume):
            if label in {"Skills", "Summary", "Education"}:
                continue
            candidates.append({"section": label, "text": text, "excerpt": text[:140]})
    return candidates


def classify_families(text: str) -> list[dict]:
    """Label the posting with every family whose clusters appear in the opening."""
    present = clusters_in_text(_opening_text(text))
    found = []
    for family in job_families():
        clusters = family["clusters"]
        hits = [cluster_id for cluster_id in clusters if cluster_id in present]
        if not hits:
            continue
        found.append(
            {
                "id": family["id"],
                "label": family["label"],
                "confidence": round(len(hits) / len(clusters), 2),
            }
        )
    found.sort(key=lambda item: (-item["confidence"], item["label"]))
    return found


def _opening_text(text: str) -> str:
    kept = []
    filled = 0
    for raw in (text or "").splitlines():
        heading = _heading_group(raw)
        if isinstance(heading, tuple) and heading[0] in {"required", "preferred", "inline"}:
            break
        if isinstance(heading, tuple) and heading[1] == "education":
            break
        kept.append(raw)
        if raw.strip():
            filled += 1
            if filled >= 24:
                break
    return "\n".join(kept)


def _score_components(evaluated: dict, families: list[dict], resume: dict) -> dict:
    required = evaluated["required"]
    preferred = evaluated["preferred"]
    responsibilities = evaluated["responsibilities"]
    relevance = [*required, *preferred, *responsibilities]
    tools = [row for row in relevance if row.get("category") == "tool"]
    domains = [row for row in relevance if row.get("category") == "domain"]
    domain_score = _coverage(domains) if domains else None
    overlap = _family_overlap(families, resume)
    if domain_score is None and overlap is None:
        domain_alignment = 0.0
    elif domain_score is None:
        domain_alignment = overlap
    elif overlap is None:
        domain_alignment = domain_score
    else:
        domain_alignment = (domain_score + overlap) / 2
    return {
        "required_coverage": _coverage(required),
        "preferred_coverage": _coverage(preferred),
        "responsibility_alignment": _coverage(responsibilities),
        "domain_alignment": domain_alignment,
        "tools_alignment": _coverage(tools),
        "evidence_quality": _evidence_quality(relevance),
    }


def _coverage(rows: list[dict]) -> float:
    weighted = [
        row
        for row in rows
        if float(row.get("weight") or 0) > 0 and row.get("category") in RELEVANCE_CATEGORIES
    ]
    total = sum(float(row["weight"]) for row in weighted)
    if total <= 0:
        return 0.0
    return sum(float(row["weight"]) for row in weighted if row.get("matched")) / total


def _family_overlap(families: list[dict], resume: dict) -> float | None:
    if not families:
        return None
    catalog = {family["id"]: family["clusters"] for family in job_families()}
    wanted = []
    for family in families:
        for cluster_id in catalog.get(family["id"], []):
            if cluster_id not in wanted:
                wanted.append(cluster_id)
    if not wanted:
        return None
    present = clusters_in_text(_resume_blob(resume))
    return sum(1 for cluster_id in wanted if cluster_id in present) / len(wanted)


def _resume_blob(resume: dict) -> str:
    return "\n".join(text for _label, text in _section_texts(resume or {}))


def _evidence_quality(rows: list[dict]) -> float:
    strengths = []
    for row in rows:
        best = 0.0
        for keyword in row.get("keywords") or []:
            evidence = keyword.get("evidence") or {}
            best = max(best, float(evidence.get("confidence") or 0))
        if best > 0:
            strengths.append(best)
    if not strengths:
        return 0.0
    return sum(strengths) / len(strengths)


def _eligibility(gate_rows: list[dict], all_rows: list[dict], resume: dict, description: str, facts: dict) -> dict:
    return {
        "degree": _status_gate(gate_rows, "degree", "This resume does not list a qualifying degree."),
        "years": _years_gate(all_rows, resume),
        "certification": _status_gate(gate_rows, "credential", "This resume does not list the certification."),
        "schedule": _stated_gate(SCHEDULE_CUE, description),
        "travel": _stated_gate(TRAVEL_CUE, description),
        "work_location": _location_gate(description, facts),
        "employment_type": _stated_gate(EMPLOYMENT_CUE, description),
    }


def _status_gate(rows: list[dict], category: str, failure: str) -> dict:
    chosen_pool = [row for row in rows if row.get("category") == category or row.get("kind") == category]
    required = [row for row in chosen_pool if row.get("group") == "required"]
    chosen = required or [row for row in chosen_pool if row.get("group") != "required"]
    if not chosen:
        return {"status": "not_stated", "detail": ""}
    if all(row.get("matched") for row in chosen):
        detail = next((row.get("detail") or "" for row in chosen if row.get("matched") and row.get("detail")), "")
        return {"status": "pass", "detail": detail}
    failed = next(row for row in chosen if not row.get("matched"))
    return {"status": "fail", "detail": failed.get("detail") or failure}


def _years_gate(rows: list[dict], resume: dict) -> dict:
    def numbers(groups: set[str]) -> list[float]:
        values = []
        for row in rows:
            if row.get("group") not in groups:
                continue
            years = row.get("years")
            if years is None:
                years = _min_years(row.get("text") or "")
            if years is not None:
                values.append(float(years))
        return values

    required = numbers({"required", "responsibility"})
    preferred = numbers({"preferred"})
    bar_values = required or preferred
    if not bar_values:
        return {"status": "not_stated", "detail": ""}
    bar = max(bar_values)
    detail = f"Posting asks for {bar:g}+ years."
    resume_years = _resume_years(resume)
    if resume_years is None:
        return {"status": "unknown", "detail": detail}
    shown = f"{detail} Resume shows about {resume_years:g} years."
    if resume_years + 1e-6 >= bar:
        return {"status": "pass", "detail": shown}
    return {"status": "fail", "detail": shown}


def _resume_years(resume: dict) -> float | None:
    spans = []
    now = date.today().year
    for key in ("work_experience", "leadership", "projects"):
        for item in (resume or {}).get(key) or []:
            if not isinstance(item, dict):
                continue
            start = item.get("start_year")
            end = now if item.get("is_current") else item.get("end_year")
            if start and end:
                spans.append(int(end) - int(start))
                continue
            years = [
                int(year)
                for year in re.findall(r"\b(?:19|20)\d{2}\b", _text(item.get("date_label") or item.get("date")))
            ]
            if len(years) >= 2:
                spans.append(max(years) - min(years))
            elif len(years) == 1 and item.get("is_current"):
                spans.append(now - years[0])
    if not spans:
        return None
    return float(sum(max(0, span) for span in spans))


def _stated_gate(pattern: re.Pattern, description: str) -> dict:
    match = pattern.search(description or "")
    if not match:
        return {"status": "not_stated", "detail": ""}
    return {"status": "unknown", "detail": re.sub(r"\s+", " ", match.group(0)).strip()}


def _location_gate(description: str, facts: dict) -> dict:
    places = list(facts.get("locations") or [])
    mode = WORK_MODE_CUE.search(description or "")
    if mode:
        places.append(mode.group(0))
    if not places:
        return {"status": "not_stated", "detail": ""}
    return {"status": "unknown", "detail": ", ".join(places)}


def _clause_matched(clause: dict, found_map: dict) -> bool:
    flags = [found_map.get(keyword, False) for keyword in clause.get("keywords") or []]
    if not flags:
        return False
    if clause.get("mode") == "any":
        return any(flags)
    return all(flags)


def _any_suggestions(keywords: list[str], requirement: str, bullets: list, skill_groups: list) -> list[dict]:
    ranked = []
    for index, keyword in enumerate(keywords):
        options = _placement_options(keyword, requirement, bullets, skill_groups)
        best = options[0] if options else None
        score = 0
        if best and best.get("bullet_id"):
            score = 2
        elif best and best.get("line_id") not in ("", "tools"):
            score = 1
        ranked.append((score, index, options))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    suggestions = []
    for _score, _index, options in ranked[:2]:
        suggestions.extend(options[:2])
    if suggestions:
        return suggestions
    if keywords:
        return [_skills_fallback(keywords[0])]
    return []


def _keyword_found(keyword: str, sections: list[tuple[str, str]], bullets: list) -> tuple[bool, str]:
    def hit(text: str) -> bool:
        if mentions(keyword, text) or _bare_tool_hit(keyword, text):
            return True
        return _keyword_pattern(keyword).search(text) is not None

    for label, text in sections:
        if hit(text):
            return True, label
    for bullet in bullets:
        if any(mentions(keyword, tag) or _norm(tag) == _norm(keyword) for tag in bullet.get("tags") or []):
            return True, "tag"
        if hit(_text(bullet.get("wording"))):
            return True, bullet.get("section") or "bullet"
    return False, ""


def _bare_tool_hit(keyword: str, text: str) -> bool:
    surface = BARE_TOOLS.get(keyword.lower())
    if not surface:
        return False
    return re.search(r"(?<!\w)" + re.escape(surface) + r"(?!\w)", text) is not None


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
                "placement_id": str(bullet.get("placement_id") or ""),
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
        "placement_id": "",
    }


def is_skill_keyword(keyword: str, row_category: str = "") -> bool:
    """A keyword that belongs in Skills: a dictionary tool, or an unknown term on a tool row."""
    known = category_for_term(keyword)
    if known:
        return known == "tool"
    return row_category == "tool"


def _with_action(item: dict, row_category: str) -> dict:
    # Missing tools are added to Skills. Only non-tool keywords on a bullet are rewrite targets.
    if item.get("placement_id") and not is_skill_keyword(item.get("keyword") or "", row_category):
        action = "rewrite"
    else:
        action = "add_skill"
    return {**item, "action": action}


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
                "placement_id": candidate.get("placement_id") or "",
            }
        )
    if not options:
        return [_skills_fallback(keyword)]
    if len(options) < 2:
        options.append(_skills_fallback(keyword))
    return options


def _heading_group(raw: str):
    cleaned = _normalize_heading(raw)
    if not cleaned:
        return None
    if PREFERRED_EDUCATION_HEADING.match(cleaned):
        return ("preferred", "education")
    if REQUIRED_EDUCATION_HEADING.match(cleaned):
        return ("required", "education")
    if BARE_EDUCATION_HEADING.match(cleaned):
        return ("inline", "education")
    if PREFERRED_HEADING.match(cleaned):
        return ("preferred", "skill")
    if REQUIRED_HEADING.match(cleaned):
        return ("required", "skill")
    if RESPONSIBILITY_HEADING.match(cleaned):
        return ("responsibility", "responsibility")
    if BOILERPLATE_HEADING.match(cleaned) or SCHEDULE_HEADING.match(cleaned):
        return "skip"
    return None


def _normalize_heading(raw: str) -> str:
    cleaned = _clean_requirement_line(raw).strip(" :.-")
    if not cleaned or len(cleaned) > 80:
        return ""
    cleaned = re.sub(r"\s*(?:&|and)\s+skills$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*/\s*you will(?:\s+have)?$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^you will have\s*/\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" :")


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
        r"\b(?:or\s+(?:an?\s+)?equivalent|or\s+(?:an?\s+)?related|related\s+field|relevant\s+field)\b|[.;]",
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
    if not _field_required(text):
        return label
    fields = _degree_fields(text)
    if len(fields) == 1:
        return f"{label} in {fields[0]}"
    return label


def _field_required(text: str) -> bool:
    return bool(_degree_fields(text)) and not re.search(
        r"related\s+field|relevant\s+field|\bequivalent\b",
        text or "",
        re.IGNORECASE,
    )


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


def _same_keyword(left: str, right: str) -> bool:
    if left.lower() == right.lower():
        return True
    return bool(is_known_term(left) and is_known_term(right) and mentions(left, right) and mentions(right, left))


def _is_camel(token: str) -> bool:
    return bool(re.search(r"[A-Z].*[A-Z]", token)) and not token.isupper()


def _dedupe_keywords(keywords: list[str]) -> list[str]:
    chosen: list[str] = []
    chosen_tokens: list[tuple[str, ...]] = []
    for keyword in keywords:
        cleaned = _clean_phrase(keyword)
        if not cleaned or _all_stopwords(cleaned) or cleaned.lower() in {"and/or", "and / or"}:
            continue
        tokens = _tokens(cleaned)
        if not tokens:
            continue
        if any(
            _same_keyword(cleaned, existing) or tokens == existing_tokens or _covers(existing_tokens, tokens)
            for existing, existing_tokens in zip(chosen, chosen_tokens)
        ):
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
    flags = re.IGNORECASE
    if (
        not is_known_term(keyword)
        and any(char.isupper() for char in keyword)
        and any(char.islower() for char in keyword)
    ):
        flags = 0
    return re.compile(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)", flags)


def _content_tokens(text: str) -> list[str]:
    return [token for token in _tokens(text) if token not in STOPWORDS and token not in GENERIC_WORDS]


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", _text(value)).strip().lower()
