import asyncio

import pytest

from app.ai_client import AiCallError, AiCompletion
from app.skill_groups import clear_cache, filter_ai_choice, recommend_group, recommend_with_ai


def group(gid, name, on_resume=True):
    return {"id": gid, "name": name, "on_resume": on_resume}


def tool(tid, name, gid, archived=False, hidden_here=False):
    return {"id": tid, "name": name, "group_id": gid, "archived": archived, "hidden_here": hidden_here}


# Arbitrary names on purpose: nothing may depend on today's Languages / Platforms / Collaboration Tools.
GROUPS = [group("g1", "Stack"), group("g2", "Cloud stuff"), group("g3", "Misc", on_resume=False)]
TOOLS = [tool("t1", "Docker", "g2"), tool("t2", "pandas", "g1"), tool("t3", "Slack", "g3")]


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield
    clear_cache()


def test_library_precedent_wins_and_reports_state():
    tools = [*TOOLS, tool("t9", "Node.js", "g3")]
    result = recommend_group("nodejs", GROUPS, tools)
    assert result["source"] == "library"
    assert result["recommended_group_id"] == "g3"
    assert result["existing"]["state"] == "group_not_on_resume"
    assert result["groups"][0]["group_id"] == "g3"


def test_hidden_and_archived_tools_are_reported():
    hidden = recommend_group("Docker", GROUPS, [tool("t1", "Docker", "g2", hidden_here=True)])
    assert hidden["existing"]["state"] == "hidden_here"
    archived = recommend_group("Docker", GROUPS, [tool("t1", "Docker", "g2", archived=True)])
    assert archived["existing"]["state"] == "archived"
    assert archived["recommended_group_id"] == "g2"


def test_related_skill_picks_the_group():
    result = recommend_group("Kubernetes", GROUPS, TOOLS)
    assert result["source"] == "related"
    assert result["recommended_group_id"] == "g2"
    assert "Docker" in result["groups"][0]["reason"]


def test_hint_matches_group_name():
    groups = [group("a", "Programming Languages"), group("b", "Teamwork")]
    result = recommend_group("Python", groups, [])
    assert (result["source"], result["recommended_group_id"]) == ("hint", "a")
    assert result["label"] == "Python"


def test_no_groups_suggests_a_new_group_name():
    result = recommend_group("Python", [], [])
    assert result["source"] == "none"
    assert result["recommended_group_id"] is None
    assert result["new_group_name"] == "Languages"


def test_unknown_term_has_no_recommendation():
    result = recommend_group("Frobnicator", GROUPS, TOOLS)
    assert result["source"] == "none"
    assert result["new_group_name"] is None
    assert [item["group_id"] for item in result["groups"]] == ["g1", "g2", "g3"]


def test_ai_is_not_called_when_a_local_step_answers():
    calls = []

    async def complete(messages, schema, name):
        calls.append(name)
        raise AssertionError("should not be called")

    result = asyncio.run(recommend_with_ai("Kubernetes", GROUPS, TOOLS, complete=complete))
    assert result["source"] == "related"
    assert calls == []


def test_ai_fallback_picks_a_listed_group_and_caches():
    calls = []

    async def complete(messages, schema, name):
        calls.append(messages)
        return AiCompletion({"group_id": "g1", "new_group_name": None, "rationale": "fits"}, "m:free")

    first = asyncio.run(recommend_with_ai("Frobnicator", GROUPS, TOOLS, complete=complete))
    second = asyncio.run(recommend_with_ai("Frobnicator", GROUPS, TOOLS, complete=complete))
    assert first["source"] == "ai" and first["recommended_group_id"] == "g1"
    assert second["recommended_group_id"] == "g1"
    assert len(calls) == 1
    sent = calls[0][1]["content"]
    assert "Frobnicator" in sent and "Docker" in sent


def test_ai_unknown_group_and_duplicate_name_are_dropped():
    assert filter_ai_choice({"group_id": "nope", "new_group_name": "stack"}, GROUPS) == (None, None)
    assert filter_ai_choice({"group_id": None, "new_group_name": "Hardware"}, GROUPS) == (None, "Hardware")
    assert filter_ai_choice({"group_id": "g2", "new_group_name": "Hardware"}, GROUPS) == ("g2", None)
    assert filter_ai_choice({"group_id": None, "new_group_name": "x" * 61}, GROUPS) == (None, None)


@pytest.mark.parametrize("status", ["unavailable", "rate_limited", "invalid"])
def test_ai_errors_keep_no_recommendation(status):
    async def complete(messages, schema, name):
        raise AiCallError(status)

    result = asyncio.run(recommend_with_ai("Frobnicator", GROUPS, TOOLS, complete=complete))
    assert result["source"] == "none"
    assert result["status"] == status
    assert result["recommended_group_id"] is None


def test_missing_key_is_unavailable_without_a_call(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    result = asyncio.run(recommend_with_ai("Frobnicator", GROUPS, TOOLS))
    assert result["status"] == "unavailable"
