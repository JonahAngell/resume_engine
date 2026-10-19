"""Pick the best existing library wording for each placed bullet, for one job. Nothing here saves.

Candidates for a placement are the other active variants of its bullet plus unused bullets of
the same role or project. Every candidate gets a deterministic job-keyword score. When AI is
available the model also scores each candidate; it can only choose among library text, so no
fabrication guard is needed. Applying a pick uses the replace-placements endpoint.
"""

import hashlib
import json
import logging

from .ai_client import AiCallError, ai_available, complete_json, model_name
from .ai_review import redact_job, scrub
from .ai_variants import has_keyword
from .job_match import extract_keywords

logger = logging.getLogger("resume_engine.ai")

PICK_PROMPT_VERSION = "1"
MAX_SLOTS = 40
MAX_CANDIDATES = 8
MAX_BODY = 400
MAX_REASON = 200
MAX_HITS = 6
# The model's best must beat the current wording by this much before we recommend a switch.
AI_MARGIN = 8
DETAILS = {
    "unavailable": "AI ranking is unavailable. Showing a job keyword ranking instead.",
    "rate_limited": "The free model is rate limited. Showing a job keyword ranking instead.",
    "invalid": "The model response could not be validated. Showing a job keyword ranking instead.",
}
_CACHE: dict[str, dict] = {}
_CACHE_MAX = 16

PICK_SYSTEM = """You choose resume wording for a specific job posting.
You get slots. Each slot is one bullet position on the resume with a list of candidate wordings from the user's library.
Return one JSON object with key slots: a list with one item per slot, each with id and scores.
scores: one item per candidate, each with key, score (0 to 100, how well that wording serves this posting), and reason (one short sentence).
Rules:
- Judge relevance to the posting's requirements, concrete outcomes, and clarity.
- Use only the candidate keys you were given. Do not write new wording."""

PICK_SCHEMA = {
    "type": "object",
    "properties": {
        "slots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "scores": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "key": {"type": "string"},
                                "score": {"type": "number"},
                                "reason": {"type": "string"},
                            },
                            "required": ["key", "score"],
                        },
                    },
                },
                "required": ["id", "scores"],
            },
        }
    },
    "required": ["slots"],
}


def _clip(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def keyword_hits(body: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if has_keyword(body, keyword)]


def build_slots(
    placements: list[dict], library: list[dict], keywords: list[str], placed_ids: list[str] | None = None
) -> list[dict]:
    """One slot per placement, with the current wording first, then the best keyword matches.

    `placements`: placement_id, bullet_id, variant_id, parent_id, section, parent_label, body.
    `library`: bullet_id, variant_id, parent_id, name, body (active rows only).
    """
    placed = {str(item) for item in placed_ids or []} | {str(row["bullet_id"]) for row in placements}
    by_parent: dict[str, list[dict]] = {}
    for row in library:
        by_parent.setdefault(str(row["parent_id"]), []).append(row)
    slots = []
    for row in placements[:MAX_SLOTS]:
        current = {
            "bullet_id": str(row["bullet_id"]),
            "variant_id": str(row["variant_id"]),
            "name": row.get("variant_name") or "Current",
            "body": row.get("body") or "",
            "current": True,
        }
        others = []
        seen = {" ".join(current["body"].split()).casefold()}
        for option in by_parent.get(str(row["parent_id"]), []):
            bullet_id = str(option["bullet_id"])
            if str(option["variant_id"]) == current["variant_id"]:
                continue
            # A bullet can appear once per resume: only this bullet's variants or unused bullets.
            if bullet_id != current["bullet_id"] and bullet_id in placed:
                continue
            folded = " ".join((option.get("body") or "").split()).casefold()
            if not folded or folded in seen:
                continue
            seen.add(folded)
            others.append(
                {
                    "bullet_id": bullet_id,
                    "variant_id": str(option["variant_id"]),
                    "name": option.get("name") or "",
                    "body": option.get("body") or "",
                    "current": False,
                }
            )
        for option in [current, *others]:
            option["keyword_hits"] = keyword_hits(option["body"], keywords)
        others.sort(key=lambda option: -len(option["keyword_hits"]))
        candidates = [current, *others[: MAX_CANDIDATES - 1]]
        for index, option in enumerate(candidates):
            option["key"] = f"c{index + 1}"
            option["score"] = None
            option["reason"] = ""
        slots.append(
            {
                "placement_id": str(row["placement_id"]),
                "parent_id": str(row["parent_id"]),
                "section": row.get("section") or "",
                "parent_label": row.get("parent_label") or "",
                "candidates": candidates,
            }
        )
    return slots


def apply_scores(slots: list[dict], data: dict) -> int:
    """Copy validated model scores onto candidates. Returns how many items were dropped."""
    by_id = {f"s{index + 1}": slot for index, slot in enumerate(slots)}
    dropped = 0
    items = data.get("slots") if isinstance(data, dict) else None
    for item in items if isinstance(items, list) else []:
        slot = by_id.get(str(item.get("id") or "")) if isinstance(item, dict) else None
        if not slot:
            dropped += 1
            continue
        by_key = {option["key"]: option for option in slot["candidates"]}
        for score in item.get("scores") or []:
            option = by_key.get(str(score.get("key") or "")) if isinstance(score, dict) else None
            value = score.get("score") if isinstance(score, dict) else None
            if not option or isinstance(value, bool) or not isinstance(value, (int, float)):
                dropped += 1
                continue
            value = value * 100 if 0 < value <= 1 else value
            option["score"] = int(round(min(100, max(0, value))))
            option["reason"] = _clip(score.get("reason"), MAX_REASON)
    return dropped


def rank(slots: list[dict], method: str) -> list[dict]:
    """Order candidates, choose a best per slot, and never pick one unused bullet for two slots."""
    taken: set[str] = set()
    for slot in slots:
        def order(option):
            hits = len(option["keyword_hits"])
            if method == "ai":
                return (-(option["score"] if option["score"] is not None else -1), -hits, not option["current"])
            return (-hits, not option["current"])

        slot["candidates"].sort(key=order)
        current = next(option for option in slot["candidates"] if option["current"])
        best = current
        for option in slot["candidates"]:
            if option["current"] or option["bullet_id"] == current["bullet_id"] or option["bullet_id"] not in taken:
                best = option
                break
        if method == "ai":
            better = (
                best["score"] is not None
                and (current["score"] is None or best["score"] >= current["score"] + AI_MARGIN)
            )
        else:
            better = len(best["keyword_hits"]) > len(current["keyword_hits"])
        if best is not current and better:
            if best["bullet_id"] != current["bullet_id"]:
                taken.add(best["bullet_id"])
        else:
            best = current
        slot["current_key"] = current["key"]
        slot["best_key"] = best["key"]
        slot["recommend"] = best is not current
        for option in slot["candidates"]:
            option["keyword_hits"] = option["keyword_hits"][:MAX_HITS]
    return slots


def _cache_key(job: str, slots: list[dict], model: str) -> str:
    shape = [[slot["placement_id"], [[o["key"], o["body"]] for o in slot["candidates"]]] for slot in slots]
    raw = json.dumps([job, shape, PICK_PROMPT_VERSION, model])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _result(status: str, method: str, slots: list[dict], model: str = "", dropped: int = 0, revision: int = 0) -> dict:
    return {
        "status": status,
        "detail": DETAILS.get(status, ""),
        "model": model,
        "method": method,
        "revision": revision,
        "slots": slots,
        "dropped": dropped,
    }


async def pick_variants(
    job_text: str,
    placements: list[dict],
    library: list[dict],
    revision: int = 0,
    use_ai: bool = True,
    placed_ids: list[str] | None = None,
    complete=None,
) -> dict:
    keywords = [item["keyword"] for item in extract_keywords(job_text or "")]
    slots = build_slots(placements, library, keywords, placed_ids)
    if not slots:
        return _result("ok", "keywords", [], revision=revision)
    if complete is None:
        complete = complete_json
        if not ai_available():
            return _result("unavailable" if use_ai else "ok", "keywords", rank(slots, "keywords"), revision=revision)
    if not use_ai or all(len(slot["candidates"]) < 2 for slot in slots):
        return _result("ok", "keywords", rank(slots, "keywords"), revision=revision)

    model = model_name()
    job = redact_job(job_text or "")[:12000]
    key = _cache_key(job, slots, model)
    cached = _CACHE.get(key)
    if cached is not None:
        return {**json.loads(json.dumps(cached)), "revision": revision}

    request = {
        "posting": job,
        "slots": [
            {
                "id": f"s{index + 1}",
                "entry": _clip(slot["parent_label"], 120),
                "candidates": [
                    {"key": option["key"], "text": _clip(scrub(option["body"], []), MAX_BODY)}
                    for option in slot["candidates"]
                ],
            }
            for index, slot in enumerate(slots)
            if len(slot["candidates"]) > 1
        ],
    }
    messages = [
        {"role": "system", "content": PICK_SYSTEM},
        {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
    ]
    # Slot ids in the request skip single-candidate slots; map them back by position.
    sent = [slot for slot in slots if len(slot["candidates"]) > 1]
    try:
        completion = await complete(messages, PICK_SCHEMA, "variant_pick")
    except AiCallError as exc:
        logger.info("variant_pick prompt=%s outcome=%s", PICK_PROMPT_VERSION, exc.status)
        return _result(exc.status, "keywords", rank(slots, "keywords"), revision=revision)
    data = getattr(completion, "data", None)
    if not isinstance(data, dict):
        return _result("invalid", "keywords", rank(slots, "keywords"), revision=revision)
    served = getattr(completion, "model", "") or model
    dropped = apply_scores(sent, data)
    scored = sum(1 for slot in sent for option in slot["candidates"] if option["score"] is not None)
    if not scored:
        return _result("invalid", "keywords", rank(slots, "keywords"), served, dropped, revision)
    logger.info(
        "variant_pick prompt=%s outcome=ok model=%s slots=%s scored=%s dropped=%s",
        PICK_PROMPT_VERSION,
        served,
        len(sent),
        scored,
        dropped,
    )
    payload = _result("ok", "ai", rank(slots, "ai"), served, dropped, revision)
    _CACHE[key] = payload
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    return json.loads(json.dumps(payload))


def clear_cache() -> None:
    _CACHE.clear()

