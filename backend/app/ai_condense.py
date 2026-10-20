"""Shrink a resume toward its page target: bullets to condense, bullets and entries to remove.

Line counts come from the editor's preview measurement. The model may only shorten wording
(every condensed draft passes the same fact guard as AI wording) and may only name bullets
and entries it was given. Without AI, or when it fails, wrapping bullets are listed for the
user to shorten and, with a job, bullets and entries that use none of its keywords are listed
for removal. Nothing here saves; applying uses the ai-condense/apply endpoint.
"""

import hashlib
import json
import logging
import math

from .ai_client import AiCallError, ai_available, complete_json, model_name
from .ai_review import redact_job, scrub
from .ai_variants import drop_reason, job_tool_terms, remember_issued
from .ai_variant_pick import keyword_hits
from .job_match import extract_keywords
from .cache import BoundedCache

logger = logging.getLogger("resume_engine.ai")

CONDENSE_PROMPT_VERSION = "1"
DEFAULT_CHARS = 95
MAX_BULLETS = 60
MAX_ENTRIES = 20
MAX_BODY = 500
MAX_REASON = 200
MAX_HITS = 6
DETAILS = {
    "unavailable": "AI suggestions are unavailable. Showing bullets that wrap and the least relevant items instead.",
    "rate_limited": "The free model is rate limited. Showing bullets that wrap and the least relevant items instead.",
    "invalid": "The model response could not be validated. Showing bullets that wrap and the least relevant items instead.",
}
_CACHE = BoundedCache(16)

CONDENSE_SYSTEM = """You help fit a resume onto its target page count.
You get the resume's bullets (with how many printed lines each takes), its entries (roles and projects), how many lines are over the target (lines_over), and roughly how many characters fit on one line (chars_per_line). A posting may be included.
Return one JSON object with keys condense, remove_bullets, and remove_entries.
condense: bullets to shorten. Each item has id, body (the shortened bullet), and reason (one short sentence). A shortened bullet must take at least one fewer line: at most chars_per_line times (lines - 1) characters.
remove_bullets: bullets to drop. Each item has id and reason.
remove_entries: whole entries to drop. Each item has id and reason.
Rules:
- Prefer condensing bullets that wrap onto a short last line (small trim_to_save_line) first.
- Suggest removals only when condensing cannot save lines_over lines. Remove the weakest or least relevant items; with a posting, the ones least relevant to it.
- Remove a whole entry only when it is clearly the weakest and lines are still short.
- Every fact in a shortened bullet must come from the original. Do not add numbers, tools, products, employers, people, places, or certifications. Keep the numbers that matter.
- Use only the ids you were given."""

CONDENSE_SCHEMA = {
    "type": "object",
    "properties": {
        "condense": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "body": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "body"],
            },
        },
        "remove_bullets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["id"],
            },
        },
        "remove_entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["id"],
            },
        },
    },
    "required": ["condense", "remove_bullets", "remove_entries"],
}


def _clip(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def lines_for(text: str, chars_per_line: int) -> int:
    return max(1, math.ceil(len(" ".join((text or "").split())) / max(1, chars_per_line)))


def prepare(
    bullets: list[dict],
    entries: list[dict],
    bullet_lines: dict[str, int],
    item_lines: dict[str, int],
    chars_per_line: int,
    keywords: list[str],
) -> tuple[list[dict], list[dict]]:
    """Attach measured lines and job keyword hits; estimate lines from length when unmeasured.

    `bullets`: placement_id, parent_id, section, parent_label, body, line_id.
    `entries`: id, section, label.
    """
    rows = []
    for row in bullets[:MAX_BULLETS]:
        body = " ".join((row.get("body") or "").split())
        if not body:
            continue
        measured = bullet_lines.get(row.get("line_id") or "")
        lines = int(measured) if isinstance(measured, int) and measured > 0 else lines_for(body, chars_per_line)
        rows.append(
            {
                **row,
                "body": body,
                "lines": lines,
                "trim": max(0, len(body) - chars_per_line * (lines - 1)) if lines > 1 else 0,
                "keyword_hits": keyword_hits(body, keywords),
            }
        )
    by_parent: dict[str, list[dict]] = {}
    for row in rows:
        by_parent.setdefault(str(row["parent_id"]), []).append(row)
    items = []
    for entry in entries[:MAX_ENTRIES]:
        own = by_parent.get(str(entry["id"]), [])
        measured = item_lines.get(str(entry["id"]))
        lines = int(measured) if isinstance(measured, int) and measured > 0 else 2 + sum(row["lines"] for row in own)
        hits = sorted({hit for row in own for hit in row["keyword_hits"]})
        items.append({**entry, "lines": lines, "bullet_count": len(own), "keyword_hits": hits})
    return rows, items


def _item(kind: str, row: dict, lines_saved: int, reason: str, body: str = "", name: str = "") -> dict:
    entry = kind == "remove_entry"
    return {
        "kind": kind,
        "id": str(row["id"] if entry else row["placement_id"]),
        "section": row.get("section") or "",
        "parent_label": row.get("label" if entry else "parent_label") or "",
        "original": "" if entry else row["body"],
        "body": body,
        "name": name,
        "lines": row["lines"],
        "lines_saved": max(0, lines_saved),
        "reason": reason,
        "keyword_hits": row["keyword_hits"][:MAX_HITS],
        "recommended": False,
    }


def validate(data: dict, bullets: list[dict], entries: list[dict], chars_per_line: int, job_terms: list[str]):
    """Keep model suggestions that name known ids and, for condensing, save a line without new facts."""
    by_bullet = {f"b{index + 1}": row for index, row in enumerate(bullets)}
    by_entry = {f"e{index + 1}": row for index, row in enumerate(entries)}
    dropped = 0
    removed_entries: list[dict] = []
    for item in data.get("remove_entries") or []:
        row = by_entry.get(str(item.get("id") or "")) if isinstance(item, dict) else None
        if not row or any(found["id"] == str(row["id"]) for found in removed_entries):
            dropped += 1
            continue
        removed_entries.append(_item("remove_entry", row, row["lines"], _clip(item.get("reason"), MAX_REASON)))
    gone = {found["id"] for found in removed_entries}
    used: set[str] = set()
    condensed: list[dict] = []
    for item in data.get("condense") or []:
        row = by_bullet.get(str(item.get("id") or "")) if isinstance(item, dict) else None
        body = _clip(item.get("body"), MAX_BODY).lstrip("•-* ").strip() if isinstance(item, dict) else ""
        if not row or row["placement_id"] in used or str(row["parent_id"]) in gone or row["lines"] < 2:
            dropped += 1
            continue
        saved = row["lines"] - lines_for(body, chars_per_line)
        if saved < 1 or drop_reason(body, row["body"], "", "", job_terms):
            dropped += 1
            continue
        used.add(row["placement_id"])
        condensed.append(
            _item("condense", row, saved, _clip(item.get("reason"), MAX_REASON), body, "Condensed")
        )
    removed: list[dict] = []
    for item in data.get("remove_bullets") or []:
        row = by_bullet.get(str(item.get("id") or "")) if isinstance(item, dict) else None
        if not row or row["placement_id"] in used or str(row["parent_id"]) in gone:
            dropped += 1
            continue
        used.add(row["placement_id"])
        removed.append(_item("remove_bullet", row, row["lines"], _clip(item.get("reason"), MAX_REASON)))
    return condensed, removed, removed_entries, dropped


def heuristic(bullets: list[dict], entries: list[dict], has_job: bool):
    """Wrapping bullets to shorten by hand, and, with a job, items that use none of its keywords."""
    wrapping = sorted((row for row in bullets if row["lines"] > 1), key=lambda row: (row["trim"], -row["lines"]))
    condensed = [
        _item(
            "condense",
            row,
            1,
            f"Wraps to {row['lines']} lines. Cutting about {row['trim']} characters saves a line."
            if row["trim"]
            else f"Wraps to {row['lines']} lines.",
        )
        for row in wrapping
    ]
    if not has_job:
        return condensed, [], []
    weak_entries = [row for row in entries if row["bullet_count"] and not row["keyword_hits"]]
    gone = {str(row["id"]) for row in weak_entries}
    removed = [
        _item("remove_bullet", row, row["lines"], "Uses none of the job's keywords.")
        for row in sorted(bullets, key=lambda row: -row["lines"])
        if not row["keyword_hits"] and str(row["parent_id"]) not in gone
    ]
    removed_entries = [
        _item("remove_entry", row, row["lines"], "None of its bullets use the job's keywords.") for row in weak_entries
    ]
    return condensed, removed, removed_entries


def recommend(condensed: list[dict], removed: list[dict], removed_entries: list[dict], lines_over: int) -> int:
    """Pre-select the fewest changes that cover lines_over: condensing first, then bullets, then entries.

    Condense items without a draft are never pre-selected. Returns the lines the selection saves.
    """
    saved = 0
    for item in sorted((item for item in condensed if item["body"]), key=lambda item: -item["lines_saved"]):
        if lines_over and saved >= lines_over:
            break
        item["recommended"] = True
        saved += item["lines_saved"]
    for group in (removed, removed_entries):
        for item in group:
            if saved >= lines_over:
                break
            item["recommended"] = True
            saved += item["lines_saved"]
    return saved


def _result(status, method, model, lines_over, chars_per_line, revision, groups=None, dropped=0) -> dict:
    condensed, removed, removed_entries = groups or ([], [], [])
    saved = recommend(condensed, removed, removed_entries, lines_over)
    return {
        "status": status,
        "detail": DETAILS.get(status, ""),
        "model": model,
        "method": method,
        "revision": revision,
        "lines_over": lines_over,
        "chars_per_line": chars_per_line,
        "recommended_lines_saved": saved,
        "items": [*condensed, *removed, *removed_entries],
        "dropped": dropped,
    }


def _cache_key(job: str, bullets: list[dict], entries: list[dict], lines_over: int, cpl: int, model: str) -> str:
    shape = [
        [[row["placement_id"], row["body"], row["lines"]] for row in bullets],
        [[row["id"], row["lines"]] for row in entries],
    ]
    raw = json.dumps([job, shape, lines_over, cpl, CONDENSE_PROMPT_VERSION, model])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def condense_resume(
    job_text: str,
    bullets: list[dict],
    entries: list[dict],
    bullet_lines: dict[str, int] | None = None,
    item_lines: dict[str, int] | None = None,
    chars_per_line: int = 0,
    lines_over: int = 0,
    revision: int = 0,
    use_ai: bool = True,
    job_id: str = "",
    complete=None,
) -> dict:
    cpl = chars_per_line if chars_per_line >= 30 else DEFAULT_CHARS
    keywords = [item["keyword"] for item in extract_keywords(job_text or "")] if job_text else []
    rows, items = prepare(bullets, entries, bullet_lines or {}, item_lines or {}, cpl, keywords)
    has_job = bool(job_text)

    def fallback(status: str, model: str = "", dropped: int = 0) -> dict:
        return _result(status, "heuristic", model, lines_over, cpl, revision, heuristic(rows, items, has_job), dropped)

    if not rows:
        return _result("ok", "heuristic", "", lines_over, cpl, revision)
    if complete is None:
        complete = complete_json
        if not ai_available():
            return fallback("unavailable" if use_ai else "ok")
    if not use_ai:
        return fallback("ok")

    model = model_name()
    job = redact_job(job_text or "")[:12000]
    key = _cache_key(job, rows, items, lines_over, cpl, model)
    cached = _CACHE.get(key)
    if cached is None:
        request = {
            "lines_over": lines_over,
            "chars_per_line": cpl,
            "posting": job or "No job chosen. Judge by impact and clarity.",
            "entries": [
                {
                    "id": f"e{index + 1}",
                    "section": row.get("section") or "",
                    "entry": _clip(scrub(row.get("label") or "", []), 120),
                    "lines": row["lines"],
                    "bullets": row["bullet_count"],
                }
                for index, row in enumerate(items)
            ],
            "bullets": [
                {
                    "id": f"b{index + 1}",
                    "entry": _clip(scrub(row.get("parent_label") or "", []), 120),
                    "text": _clip(scrub(row["body"], []), MAX_BODY),
                    "lines": row["lines"],
                    "trim_to_save_line": row["trim"],
                }
                for index, row in enumerate(rows)
            ],
        }
        messages = [
            {"role": "system", "content": CONDENSE_SYSTEM},
            {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
        ]
        try:
            completion = await complete(messages, CONDENSE_SCHEMA, "resume_condense")
        except AiCallError as exc:
            logger.info("resume_condense prompt=%s outcome=%s", CONDENSE_PROMPT_VERSION, exc.status)
            return fallback(exc.status)
        data = getattr(completion, "data", None)
        if not isinstance(data, dict):
            return fallback("invalid")
        cached = {"data": data, "model": getattr(completion, "model", "") or model}
        _CACHE.set(key, cached)
    served = cached["model"]
    job_terms = job_tool_terms(job_text or "")
    condensed, removed, removed_entries, dropped = validate(cached["data"], rows, items, cpl, job_terms)
    if not (condensed or removed or removed_entries) and dropped:
        return fallback("invalid", served, dropped)
    for item in condensed:
        remember_issued(item["id"], [{"body": item["body"]}], served, job_id)
    logger.info(
        "resume_condense prompt=%s outcome=ok model=%s condense=%s remove=%s entries=%s dropped=%s",
        CONDENSE_PROMPT_VERSION,
        served,
        len(condensed),
        len(removed),
        len(removed_entries),
        dropped,
    )
    return _result("ok", "ai", served, lines_over, cpl, revision, (condensed, removed, removed_entries), dropped)


def clear_cache() -> None:
    _CACHE.clear()
