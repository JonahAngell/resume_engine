"""Choose which library records and wordings a new resume should start with, for one job.

Nothing here saves; the caller builds the resume from the returned Selection. The model only
picks among library keys (e1, b4v2, s1, ...), never database ids, and never writes text, so no
fabrication guard is needed. Every record also gets a deterministic job-keyword score, which
trims the model's picks to a one-page budget and serves as the whole answer when AI is
unavailable or its response cannot be used.
"""

import json
import logging
from uuid import UUID

from .ai_client import AiCallError, ai_available, complete_json, model_name
from .ai_review import redact_job, scrub
from .ai_variant_pick import keyword_hits
from .job_match import extract_keywords
from .resume_variants import Selection

logger = logging.getLogger("resume_engine.ai")

RECOMMEND_PROMPT_VERSION = "1"
SECTIONS = {"employment": "work_experience", "project": "projects", "leadership": "leadership"}
# One-page budget.
MAX_ENTRIES = {"employment": 4, "project": 3, "leadership": 2}
MIN_BULLETS = 2
MAX_BULLETS_PER_ENTRY = 5
MAX_BULLETS = 16
# Prompt size limits.
MAX_ENTRIES_SENT = 30
MAX_VARIANTS_PER_BULLET = 3
MAX_VARIANTS_SENT = 180
MAX_BODY = 300
MAX_REASON = 200
DETAILS = {
    "unavailable": "AI is unavailable, so records were chosen by matching job keywords.",
    "rate_limited": "The free model is rate limited, so records were chosen by matching job keywords.",
    "invalid": "The model response could not be used, so records were chosen by matching job keywords.",
}

RECOMMEND_SYSTEM = f"""You build a one-page resume for a specific job posting from the user's library.
The library lists entries (jobs, projects, leadership roles), each with bullets. A bullet can have several wordings (variants); pick at most one wording per bullet.
Return one JSON object with keys:
- entries: list of {{key, bullets, reason}} for the entries to include, most relevant first. bullets is a list of variant keys (like "b3v2") from that entry, best first. reason is one short sentence on why the entry fits the posting.
- summary: the key of the best summary, or "" if none fits.
- skill_groups: list of skill group keys relevant to the posting.
- custom_sections: list of custom section keys relevant to the posting.
- interests: true to include personal interests.
Rules:
- Fit one page: at most {MAX_ENTRIES['employment']} jobs, {MAX_ENTRIES['project']} projects, {MAX_ENTRIES['leadership']} leadership roles, {MIN_BULLETS} to {MAX_BULLETS_PER_ENTRY} bullets per entry, {MAX_BULLETS} bullets in total.
- Prefer wording that shows the posting's requirements, concrete outcomes, and its keywords.
- Keep the most recent job unless it is clearly irrelevant.
- Use only keys you were given. Do not write new wording."""

RECOMMEND_SCHEMA = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["key", "bullets"],
            },
        },
        "summary": {"type": "string"},
        "skill_groups": {"type": "array", "items": {"type": "string"}},
        "custom_sections": {"type": "array", "items": {"type": "string"}},
        "interests": {"type": "boolean"},
    },
    "required": ["entries"],
}


def _clip(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _active(row) -> bool:
    return not row.get("archived_at")


def _entry_label(row) -> str:
    parts = [row.get("title"), row.get("organization") or row.get("name"), row.get("subtitle")]
    seen, label = set(), []
    for part in parts:
        text = _clip(part, 120)
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            label.append(text)
    dates = _clip(row.get("date_label"), 60)
    if not dates and row.get("start_year"):
        end = "Present" if row.get("is_current") else row.get("end_year") or ""
        dates = f"{row['start_year']}–{end}".rstrip("–")
    return " — ".join(label) + (f" ({dates})" if dates else "")


def _secrets(library: dict) -> list[str]:
    values = []
    for profile in library.get("profiles") or []:
        values += [profile.get(key) for key in ("name", "phone", "email", "linkedin_label", "linkedin_url")]
        for variant in profile.get("field_variants") or []:
            values += [variant.get(key) for key in ("display_name", "phone", "email", "linkedin_url")]
    return [str(value) for value in values if value and len(str(value)) >= 3]


def build_catalog(library: dict, keywords: list[str]) -> dict:
    """Active library records with short keys and keyword scores."""
    entries, variant_count = [], 0
    for kind in ("employment", "project", "leadership"):
        for order, row in enumerate(item for item in library.get(kind) or [] if _active(item)):
            bullets: dict[str, dict] = {}
            for line in row.get("bullets") or []:
                if line.get("archived_at") or line.get("variant_archived_at") or not line.get("variant_id"):
                    continue
                body = line.get("body") or ""
                if not body.strip():
                    continue
                bullet = bullets.setdefault(
                    str(line["id"]),
                    {"bullet_id": str(line["id"]), "sort_order": line.get("sort_order") or 0, "variants": []},
                )
                bullet["variants"].append(
                    {
                        "variant_id": str(line["variant_id"]),
                        "body": body,
                        "is_default": bool(line.get("is_default")),
                        "hits": keyword_hits(body, keywords),
                    }
                )
            label = _entry_label(row)
            ranked = []
            for bullet in bullets.values():
                bullet["variants"].sort(key=lambda v: (-len(v["hits"]), not v["is_default"]))
                bullet["score"] = len(bullet["variants"][0]["hits"])
                ranked.append(bullet)
            ranked.sort(key=lambda b: (-b["score"], b["sort_order"]))
            entries.append(
                {
                    "kind": kind,
                    "item_id": str(row["id"]),
                    "label": label,
                    "order": order,
                    "bullets": ranked,
                    "score": len(keyword_hits(label, keywords))
                    + sum(b["score"] for b in ranked[:MAX_BULLETS_PER_ENTRY]),
                }
            )
    # Most relevant entries get keys first, so a trimmed prompt keeps the best of the library.
    entries.sort(key=lambda e: (-e["score"], e["kind"] != "employment", e["order"]))
    for index, entry in enumerate(entries):
        entry["key"] = f"e{index + 1}"
    bullet_number = 0
    for entry in entries:
        for bullet in entry["bullets"]:
            bullet_number += 1
            bullet["key"] = f"b{bullet_number}"
            for index, variant in enumerate(bullet["variants"]):
                variant["key"] = f"b{bullet_number}v{index + 1}"
                variant_count += 1
    summaries = [row for row in library.get("summary_variants") or [] if _active(row)]
    summary_rows = [
        {
            "key": f"s{index + 1}",
            "id": str(row["id"]),
            "body": row.get("body") or "",
            "is_default": (row.get("name") or "").strip().lower() == "default",
            "hits": keyword_hits(row.get("body") or "", keywords),
        }
        for index, row in enumerate(summaries)
    ]
    groups = []
    for index, row in enumerate(item for item in library.get("tool_groups") or [] if _active(item)):
        tools = [tool.get("name") or "" for tool in row.get("items") or [] if _active(tool)]
        text = " ".join([row.get("name") or "", *tools])
        groups.append(
            {
                "key": f"g{index + 1}",
                "id": str(row["id"]),
                "name": row.get("name") or "",
                "tools": tools,
                "hits": keyword_hits(text, keywords),
            }
        )
    custom = []
    for index, row in enumerate(item for item in library.get("custom_sections") or [] if _active(item)):
        text = " ".join(
            " ".join(str(entry.get(key) or "") for key in ("primary_text", "secondary_text"))
            for entry in row.get("entries") or []
            if _active(entry)
        )
        custom.append(
            {
                "key": f"x{index + 1}",
                "id": str(row["id"]),
                "title": row.get("title") or "",
                "text": text,
                "hits": keyword_hits(f"{row.get('title') or ''} {text}", keywords),
            }
        )
    return {
        "entries": entries,
        "summaries": summary_rows,
        "groups": groups,
        "custom": custom,
        "education": [str(row["id"]) for row in library.get("education") or [] if _active(row)],
        "interests": [str(row["id"]) for row in library.get("interests") or [] if _active(row)],
        "variant_count": variant_count,
    }


def _prompt(catalog: dict, job: str, secrets: list[str]) -> dict:
    sent, budget = [], MAX_VARIANTS_SENT
    for entry in catalog["entries"][:MAX_ENTRIES_SENT]:
        bullets = []
        for bullet in entry["bullets"]:
            variants = bullet["variants"][:MAX_VARIANTS_PER_BULLET][: max(budget, 0)]
            if not variants:
                break
            budget -= len(variants)
            bullets.append(
                {
                    "key": bullet["key"],
                    "variants": [
                        {"key": v["key"], "text": _clip(scrub(v["body"], secrets), MAX_BODY)} for v in variants
                    ],
                }
            )
        sent.append(
            {
                "key": entry["key"],
                "type": {"employment": "job", "project": "project", "leadership": "leadership"}[entry["kind"]],
                "title": _clip(scrub(entry["label"], secrets), 200),
                "bullets": bullets,
            }
        )
    return {
        "posting": job,
        "entries": sent,
        "summaries": [
            {"key": s["key"], "text": _clip(scrub(s["body"], secrets), 600)} for s in catalog["summaries"][:8]
        ],
        "skill_groups": [
            {"key": g["key"], "name": _clip(g["name"], 80), "skills": [_clip(t, 60) for t in g["tools"][:30]]}
            for g in catalog["groups"]
        ],
        "custom_sections": [
            {"key": c["key"], "title": _clip(c["title"], 80), "text": _clip(scrub(c["text"], secrets), 400)}
            for c in catalog["custom"]
        ],
    }


def _keyword_choice(catalog: dict) -> dict:
    """The deterministic pick: best-scoring entries and wordings within the budget."""
    entries = []
    for kind, limit in MAX_ENTRIES.items():
        rows = [entry for entry in catalog["entries"] if entry["kind"] == kind]
        if kind == "employment":
            # Jobs stay in library order (usually most recent first) and fill the budget.
            rows.sort(key=lambda e: (-e["score"], e["order"]))
            rows = rows[:limit]
        else:
            rows = [entry for entry in rows if entry["score"] > 0][:limit]
            if not rows and kind == "project" and not any(e["kind"] == "employment" for e in catalog["entries"]):
                rows = [entry for entry in catalog["entries"] if entry["kind"] == kind][:2]
        for entry in rows:
            entries.append(
                {
                    "entry": entry,
                    "variants": [bullet["variants"][0] for bullet in entry["bullets"][:MAX_BULLETS_PER_ENTRY]],
                    "reason": "",
                }
            )
    summaries = sorted(catalog["summaries"], key=lambda s: (-len(s["hits"]), not s["is_default"]))
    groups = [g for g in catalog["groups"] if g["hits"]] or catalog["groups"]
    return {
        "entries": entries,
        "summary": summaries[0] if summaries else None,
        "groups": groups,
        "custom": [c for c in catalog["custom"] if c["hits"]],
        "interests": False,
    }


def _model_choice(catalog: dict, data: dict) -> tuple[dict | None, int]:
    """Map the model's keys back to records. Returns (choice or None, dropped count)."""
    dropped = 0
    by_entry = {entry["key"]: entry for entry in catalog["entries"]}
    used_entries, counts, entries = set(), {kind: 0 for kind in MAX_ENTRIES}, []
    items = data.get("entries") if isinstance(data, dict) else None
    for item in items if isinstance(items, list) else []:
        entry = by_entry.get(str(item.get("key") or "")) if isinstance(item, dict) else None
        if not entry or entry["key"] in used_entries or counts[entry["kind"]] >= MAX_ENTRIES[entry["kind"]]:
            dropped += 1
            continue
        variants_by_key = {
            variant["key"]: (bullet, variant) for bullet in entry["bullets"] for variant in bullet["variants"]
        }
        chosen, used_bullets = [], set()
        for key in item.get("bullets") or []:
            found = variants_by_key.get(str(key))
            if not found or found[0]["key"] in used_bullets:
                dropped += 1
                continue
            used_bullets.add(found[0]["key"])
            chosen.append(found[1])
        # An entry the model picked without usable bullets still gets its best wording.
        if not chosen:
            chosen = [bullet["variants"][0] for bullet in entry["bullets"][:MIN_BULLETS]]
        used_entries.add(entry["key"])
        counts[entry["kind"]] += 1
        entries.append(
            {"entry": entry, "variants": chosen[:MAX_BULLETS_PER_ENTRY], "reason": _clip(item.get("reason"), MAX_REASON)}
        )
    if not entries:
        return None, dropped
    summaries = {s["key"]: s for s in catalog["summaries"]}
    summary = summaries.get(str(data.get("summary") or ""))
    groups_by_key = {g["key"]: g for g in catalog["groups"]}
    groups = [groups_by_key[str(k)] for k in data.get("skill_groups") or [] if str(k) in groups_by_key]
    custom_by_key = {c["key"]: c for c in catalog["custom"]}
    custom = [custom_by_key[str(k)] for k in data.get("custom_sections") or [] if str(k) in custom_by_key]
    return {
        "entries": entries,
        "summary": summary,
        "groups": groups or [g for g in catalog["groups"] if g["hits"]] or catalog["groups"],
        "custom": custom,
        "interests": data.get("interests") is True,
    }, dropped


def _fit_page(choice: dict) -> dict:
    """Trim the lowest-scoring bullets until the total fits, never below the per-entry minimum."""
    total = sum(len(item["variants"]) for item in choice["entries"])
    while total > MAX_BULLETS:
        candidates = [item for item in choice["entries"] if len(item["variants"]) > MIN_BULLETS]
        if not candidates:
            break
        item = max(candidates, key=lambda i: (len(i["variants"]), -len(i["variants"][-1]["hits"])))
        item["variants"].pop()
        total -= 1
    return choice


def _selection(catalog: dict, choice: dict) -> Selection:
    selection = Selection()
    content = selection.items.setdefault("content_item", {})
    for item in choice["entries"]:
        content[UUID(item["entry"]["item_id"])] = None
        for variant in item["variants"]:
            bullet = next(b for b in item["entry"]["bullets"] if variant in b["variants"])
            selection.bullets[UUID(bullet["bullet_id"])] = UUID(variant["variant_id"])
    selection.items["education_item"] = {UUID(item): None for item in catalog["education"]}
    selection.items["tool_group"] = {UUID(group["id"]): None for group in choice["groups"]}
    selection.items["custom_section"] = {UUID(section["id"]): None for section in choice["custom"]}
    if choice["interests"]:
        selection.items["interest"] = {UUID(item): None for item in catalog["interests"]}
    if choice["summary"]:
        selection.summary_id = UUID(choice["summary"]["id"])
    return selection


def _result(status, method, catalog, choice, model="", dropped=0, keywords=()):
    picked = [
        {
            "section": SECTIONS[item["entry"]["kind"]],
            "label": item["entry"]["label"],
            "bullets": len(item["variants"]),
            "reason": item["reason"],
        }
        for item in choice["entries"]
    ]
    return {
        "status": status,
        "detail": DETAILS.get(status, ""),
        "model": model,
        "method": method,
        "dropped": dropped,
        "keywords": list(keywords)[:12],
        "entries": picked,
        "entry_count": len(picked),
        "bullet_count": sum(item["bullets"] for item in picked),
        "selection": _selection(catalog, choice),
    }


async def recommend_resume(job_text: str, library: dict, complete=None) -> dict:
    keywords = [item["keyword"] for item in extract_keywords(job_text or "")]
    catalog = build_catalog(library, keywords)

    def fallback(status, model="", dropped=0):
        return _result(status, "keywords", catalog, _fit_page(_keyword_choice(catalog)), model, dropped, keywords)

    if complete is None:
        complete = complete_json
        if not ai_available():
            return fallback("unavailable")
    if not catalog["entries"]:
        return fallback("ok")
    request = _prompt(catalog, redact_job(job_text or "")[:12000], _secrets(library))
    messages = [
        {"role": "system", "content": RECOMMEND_SYSTEM},
        {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
    ]
    try:
        completion = await complete(messages, RECOMMEND_SCHEMA, "resume_recommend")
    except AiCallError as exc:
        logger.info("resume_recommend prompt=%s outcome=%s", RECOMMEND_PROMPT_VERSION, exc.status)
        return fallback(exc.status)
    data = getattr(completion, "data", None)
    served = getattr(completion, "model", "") or model_name()
    choice, dropped = _model_choice(catalog, data if isinstance(data, dict) else {})
    if choice is None:
        logger.info("resume_recommend prompt=%s outcome=invalid model=%s", RECOMMEND_PROMPT_VERSION, served)
        return fallback("invalid", served, dropped)
    logger.info(
        "resume_recommend prompt=%s outcome=ok model=%s entries=%s dropped=%s",
        RECOMMEND_PROMPT_VERSION,
        served,
        len(choice["entries"]),
        dropped,
    )
    return _result("ok", "ai", catalog, _fit_page(choice), served, dropped, keywords)
