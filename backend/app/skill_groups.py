"""Pick a Skills group for a missing tool: library, related skills and hints first, AI last.

Group names belong to the user, so nothing here names a group. The model is asked only when
every local step comes back empty, and it sees group and tool names, nothing else.
"""

import hashlib
import json
import logging
import re

from .ai_client import AiCallError, ai_available, complete_json, model_name
from .related_skills import (
    DICTIONARY,
    canonical_term,
    combination_mention,
    display_for,
    hint_words,
    hints_for_term,
    related_mention,
)
from .cache import BoundedCache

logger = logging.getLogger("resume_engine.ai")

SKILL_PROMPT_VERSION = "1"
MAX_GROUP_NAME = 60
MAX_TOOLS_SENT = 10
_CACHE = BoundedCache(64)

SKILL_SYSTEM = """You file one skill into a resume's Skills section.
You get the skill and the user's existing skill groups, each with an id, a name, and some tools already in it.
Return one JSON object with keys group_id, new_group_name, and rationale.
group_id: the id of the best existing group, copied exactly, or null if none fits.
new_group_name: a short group name (at most 4 words) only when no existing group fits, else null.
rationale: one short sentence.
Do not invent ids."""

SKILL_SCHEMA = {
    "type": "object",
    "properties": {
        "group_id": {"type": ["string", "null"]},
        "new_group_name": {"type": ["string", "null"]},
        "rationale": {"type": "string"},
    },
    "required": ["group_id", "new_group_name", "rationale"],
}


def _fold(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def same_skill(left: str, right: str) -> bool:
    """True when two names are one skill, through dictionary aliases or plain case folding."""
    if _fold(left) == _fold(right):
        return True
    a, b = canonical_term(left), canonical_term(right)
    return bool(a) and a == b


def _existing(keyword: str, groups: list[dict], tools: list[dict]) -> dict | None:
    group_by_id = {group["id"]: group for group in groups}
    matches = [tool for tool in tools if same_skill(tool["name"], keyword)]
    if not matches:
        return None

    def rank(tool):
        group = group_by_id.get(tool["group_id"])
        active = not tool.get("archived") and group is not None
        visible = active and group.get("on_resume") and not tool.get("hidden_here")
        return (not visible, not active, not (group or {}).get("on_resume"))

    tool = sorted(matches, key=rank)[0]
    group = group_by_id.get(tool["group_id"])
    if tool.get("archived") or group is None:
        state = "archived"
    elif not group.get("on_resume"):
        state = "group_not_on_resume"
    elif tool.get("hidden_here"):
        state = "hidden_here"
    else:
        state = "on_resume"
    return {
        "tool_id": tool["id"],
        "group_id": tool["group_id"] if group else None,
        "group_name": group["name"] if group else tool.get("group_name") or "",
        "name": tool["name"],
        "state": state,
    }


def _related_scores(keyword: str, groups: list[dict], tools: list[dict]) -> dict[str, tuple[float, str]]:
    clusters = DICTIONARY._clusters_for(keyword)
    scores: dict[str, tuple[float, str]] = {}
    for group in groups:
        names = [tool["name"] for tool in tools if tool["group_id"] == group["id"] and not tool.get("archived")]
        if not names:
            continue
        text = ", ".join(names)
        related = related_mention(keyword, text)
        combo = None if related else combination_mention(keyword, text)
        if not related and not combo:
            continue
        shared = sum(1 for name in names if clusters & DICTIONARY._clusters_for(name))
        score = (4 if related else 3) + shared
        link = related or combo
        # Show the user's own spelling of the tool, not the dictionary's.
        link = next((name for name in names if same_skill(name, link)), link)
        reason = f"{group['name']} already lists {link}, which is related to {display_for(keyword)}."
        scores[group["id"]] = (score, reason)
    return scores


def _hint_scores(keyword: str, groups: list[dict]) -> dict[str, tuple[float, str]]:
    hints = hints_for_term(keyword)
    scores: dict[str, tuple[float, str]] = {}
    for group in groups:
        words = hint_words(group["name"])
        best = 0.0
        for position, hint_id in enumerate(hints):
            hint = DICTIONARY.group_hints.get(hint_id)
            if hint and words & hint["words"]:
                best = max(best, float(len(hints) - position))
        if best:
            scores[group["id"]] = (best, f"Matches the group name {group['name']}.")
    return scores


def _new_group_name(keyword: str, groups: list[dict]) -> str | None:
    names = {_fold(group["name"]) for group in groups}
    for hint_id in hints_for_term(keyword):
        title = (DICTIONARY.group_hints.get(hint_id) or {}).get("title")
        if title and _fold(title) not in names:
            return title
    return None


def recommend_group(keyword: str, groups: list[dict], tools: list[dict]) -> dict:
    """Run the local ladder. `groups` are active groups, `tools` include archived ones.

    groups: {id, name, on_resume, sort_order}
    tools:  {id, name, group_id, archived, hidden_here}
    """
    label = display_for(keyword)
    existing = _existing(keyword, groups, tools)
    source = "none"
    recommended = None
    reasons: dict[str, str] = {}
    scores: dict[str, float] = {}

    if existing and existing["group_id"]:
        source, recommended = "library", existing["group_id"]
        reasons[recommended] = f"Already in your {existing['group_name']} group."
    else:
        for step, found in (("related", _related_scores(keyword, groups, tools)), ("hint", _hint_scores(keyword, groups))):
            if not found:
                continue
            for group_id, (score, reason) in found.items():
                scores[group_id] = score
                reasons[group_id] = reason
            recommended = max(found, key=lambda group_id: (found[group_id][0], -_order(groups, group_id)))
            source = step
            break

    new_group = None
    if recommended is None:
        new_group = _new_group_name(keyword, groups)

    return {
        "label": label,
        "existing": existing,
        "groups": _ordered(groups, recommended, reasons, scores),
        "recommended_group_id": recommended,
        "new_group_name": new_group,
        "source": source,
        "status": "ok",
    }


def _order(groups: list[dict], group_id: str) -> int:
    for index, group in enumerate(groups):
        if group["id"] == group_id:
            return index
    return len(groups)


def _ordered(groups, recommended, reasons, scores) -> list[dict]:
    def rank(item):
        index, group = item
        return (group["id"] != recommended, -scores.get(group["id"], 0), not group.get("on_resume"), index)

    return [
        {
            "group_id": group["id"],
            "name": group["name"],
            "on_resume": bool(group.get("on_resume")),
            "score": float(scores.get(group["id"], 0)),
            "reason": reasons.get(group["id"], ""),
        }
        for _index, group in sorted(enumerate(groups), key=rank)
    ]


def _cache_key(keyword: str, groups: list[dict], tools: list[dict], model: str) -> str:
    shape = sorted(
        (
            _fold(group["name"]),
            sorted(_fold(tool["name"]) for tool in tools if tool["group_id"] == group["id"] and not tool.get("archived")),
        )
        for group in groups
    )
    raw = json.dumps([canonical_term(keyword) or _fold(keyword), shape, SKILL_PROMPT_VERSION, model])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def filter_ai_choice(data: dict, groups: list[dict]) -> tuple[str | None, str | None]:
    ids = {group["id"] for group in groups}
    names = {_fold(group["name"]) for group in groups}
    group_id = data.get("group_id") if isinstance(data.get("group_id"), str) else None
    if group_id not in ids:
        group_id = None
    name = data.get("new_group_name") if isinstance(data.get("new_group_name"), str) else None
    name = " ".join((name or "").split()) or None
    if name and (len(name) > MAX_GROUP_NAME or _fold(name) in names):
        name = None
    if group_id:
        name = None
    return group_id, name


async def recommend_with_ai(keyword: str, groups: list[dict], tools: list[dict], complete=None) -> dict:
    """Local ladder, then the model only when the ladder found nothing."""
    local = recommend_group(keyword, groups, tools)
    if local["source"] != "none":
        return local
    model = model_name()
    if complete is None:
        complete = complete_json
        if not ai_available():
            return {**local, "status": "unavailable"}
    key = _cache_key(keyword, groups, tools, model)
    cached = _CACHE.get(key)
    if cached is None:
        listed = [
            {
                "id": group["id"],
                "name": group["name"],
                "tools": [tool["name"] for tool in tools if tool["group_id"] == group["id"] and not tool.get("archived")][:MAX_TOOLS_SENT],
            }
            for group in groups
        ]
        messages = [
            {"role": "system", "content": SKILL_SYSTEM},
            {"role": "user", "content": json.dumps({"skill": local["label"], "groups": listed}, ensure_ascii=False)},
        ]
        try:
            result = await complete(messages, SKILL_SCHEMA, "skill_group")
        except AiCallError as exc:
            logger.info("skill_group prompt=%s outcome=%s", SKILL_PROMPT_VERSION, exc.status)
            return {**local, "status": exc.status}
        data = getattr(result, "data", None)
        if not isinstance(data, dict):
            return {**local, "status": "invalid"}
        group_id, name = filter_ai_choice(data, groups)
        cached = {"group_id": group_id, "new_group_name": name, "model": getattr(result, "model", "") or model}
        logger.info(
            "skill_group prompt=%s outcome=ok model=%s kept_group=%s kept_name=%s",
            SKILL_PROMPT_VERSION,
            cached["model"],
            bool(group_id),
            bool(name),
        )
        _CACHE.set(key, cached)
    group_id, name = cached["group_id"], cached["new_group_name"]
    if not group_id and not name:
        return {**local, "status": "ok", "model": cached["model"]}
    reasons = {group_id: "Suggested by AI."} if group_id else {}
    return {
        **local,
        "groups": _ordered(groups, group_id, reasons, {}),
        "recommended_group_id": group_id,
        "new_group_name": name or local["new_group_name"],
        "source": "ai",
        "status": "ok",
        "model": cached["model"],
    }


def clear_cache() -> None:
    _CACHE.clear()
