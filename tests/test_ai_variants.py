import asyncio
import json

import pytest

from app.ai_client import AiCallError, AiCompletion, parse_json_content
from app.ai_variants import clear_cache, drop_reason, filter_drafts, issued_draft, suggest_variants

ORIGINAL = "Owned budgeting reviews for regional teams"
JOB = "We need financial forecasting experience. Tools: Anaplan, Excel."


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield
    clear_cache()


def draft(body, name="Angle", rationale="Fits."):
    return {"name": name, "body": body, "rationale": rationale}


def reply(*bodies, model="m:free"):
    async def complete(messages, schema, name):
        complete.calls.append(messages)
        return AiCompletion({"drafts": [draft(body) for body in bodies], "extra": 1}, model)

    complete.calls = []
    return complete


def test_drafts_parse_from_fenced_json():
    content = "```json\n" + json.dumps({"drafts": [draft("Led budgeting reviews for regional teams")]}) + "\n```"
    kept, dropped = filter_drafts(parse_json_content(content), ORIGINAL, "", "", [])
    assert [item["body"] for item in kept] == ["Led budgeting reviews for regional teams"]
    assert dropped == 0


def test_unknown_fields_are_ignored_and_drafts_are_capped():
    data = {"drafts": [{**draft(f"Ran budgeting reviews for regional teams, round {word}"), "x": 1} for word in "abcdefg"]}
    kept, _ = filter_drafts(data, ORIGINAL, "", "", [])
    assert len(kept) == 5
    assert set(kept[0]) == {"name", "body", "rationale"}


@pytest.mark.parametrize(
    "body,reason",
    [
        ("Owned budgeting reviews for 12 regional teams", "number"),
        ("Cut costs 30% through budgeting reviews for regional teams", "number"),
        ("Owned budgeting reviews for dozens of regional teams", "number"),
        ("Owned budgeting reviews in Excel for regional teams", "tool"),
        ("Owned Anaplan budgeting reviews for regional teams", "tool"),
        ("Owned budgeting reviews for regional teams at Contoso", "proper_noun"),
        ("Owned budgeting reviews for regional EMEA teams", "proper_noun"),
        (ORIGINAL.upper().lower(), "unchanged"),
        ("", "empty"),
        ("Owned budgeting reviews " + "and more " * 40, "length"),
    ],
)
def test_unsafe_drafts_are_dropped(body, reason):
    assert drop_reason(body, ORIGINAL, "Financial Forecasting", "domain", ["Anaplan", "Excel"]) == reason


def test_soft_keyword_may_shape_wording():
    body = "Owned budgeting reviews and financial forecasting for regional teams"
    assert drop_reason(body, ORIGINAL, "Financial Forecasting", "domain", ["Anaplan"]) == ""


def test_guarded_keyword_is_dropped():
    body = "Owned budgeting reviews for regional teams as a PMP"
    assert drop_reason(body, ORIGINAL, "PMP", "credential", []) == "guarded_keyword"


def test_dedupe_against_original_and_siblings():
    data = {"drafts": [draft(ORIGINAL), draft("Led budgeting reviews for regional teams"), draft("led  budgeting reviews for regional teams")]}
    kept, dropped = filter_drafts(data, ORIGINAL, "", "", [])
    assert len(kept) == 1 and dropped == 2


def test_suggest_returns_safe_drafts_and_remembers_them():
    complete = reply("Led budgeting reviews for regional teams", "Owned budgeting reviews for 12 regional teams")
    result = asyncio.run(
        suggest_variants(ORIGINAL, JOB, "Financial forecasting", "Financial Forecasting", "domain",
                         placement_id="p1", job_id="j1", complete=complete)
    )
    assert result["status"] == "ok"
    assert [item["body"] for item in result["drafts"]] == ["Led budgeting reviews for regional teams"]
    assert result["dropped"] == 1
    assert issued_draft("p1", "Led budgeting reviews for regional teams", "j1") == "m:free"
    assert issued_draft("p1", "Led budgeting reviews for regional teams", "other-job") is None
    assert issued_draft("p1", "Something I wrote", "j1") is None


def test_cache_hit_skips_the_call():
    complete = reply("Led budgeting reviews for regional teams")
    for _ in range(2):
        asyncio.run(suggest_variants(ORIGINAL, JOB, "req", "kw", complete=complete))
    assert len(complete.calls) == 1


def test_contact_details_are_not_sent():
    complete = reply("Led budgeting reviews")
    asyncio.run(suggest_variants(ORIGINAL + " mail me@example.com", JOB + " https://x.example/apply", "req", "kw", complete=complete))
    sent = complete.calls[0][1]["content"]
    assert "me@example.com" not in sent and "x.example" not in sent


@pytest.mark.parametrize("status", ["unavailable", "rate_limited", "invalid"])
def test_each_failure_status_is_returned(status):
    async def complete(messages, schema, name):
        raise AiCallError(status)

    result = asyncio.run(suggest_variants(ORIGINAL, JOB, "req", "kw", complete=complete))
    assert result["status"] == status
    assert result["drafts"] == []
    assert "unchanged" in result["detail"]


def test_missing_key_or_paid_model_is_unavailable(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    assert asyncio.run(suggest_variants(ORIGINAL, JOB, "req", "kw"))["status"] == "unavailable"
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-paid")
    assert asyncio.run(suggest_variants(ORIGINAL, JOB, "req", "kw"))["status"] == "unavailable"


def test_part_of_a_soft_keyword_is_allowed_but_tools_are_not():
    original = "Turns crew schedules into decisions"
    assert drop_reason("Turns crew schedules into forecasting decisions", original, "Financial Forecasting", "domain", []) == ""
    assert drop_reason("Turns crew schedules into Python decisions", original, "Python Scripting", "domain", []) == "tool"


def test_keyword_mode_drops_drafts_without_the_keyword():
    data = {"drafts": [draft("Led budgeting reviews for regional teams"), draft("Led budgeting reviews and financial forecasting for regional teams")]}
    kept, dropped = filter_drafts(data, ORIGINAL, "Financial Forecasting", "domain", [], require_keyword=True)
    assert [item["body"] for item in kept] == ["Led budgeting reviews and financial forecasting for regional teams"]
    assert dropped == 1
    assert drop_reason("Led budgeting reviews for regional teams", ORIGINAL, "Financial Forecasting", "domain", [], require_keyword=True) == "missing_keyword"


def test_keyword_mode_accepts_a_dictionary_form_of_the_keyword():
    original = "Improved onboarding flows to lift conversion"
    body = "Ran A/B testing on onboarding flows to lift conversion"
    assert drop_reason(body, original, "A/B Testing", "methodology", ["A/B Testing"], require_keyword=True) == ""


def test_keyword_mode_never_lets_a_guarded_keyword_in():
    body = "Owned budgeting reviews for regional teams in Anaplan"
    assert drop_reason(body, ORIGINAL, "Anaplan", "tool", ["Anaplan"], require_keyword=True) == "guarded_keyword"


def test_keyword_mode_prompt_asks_for_the_keyword_and_reports_no_fit():
    async def complete(messages, schema, name):
        complete.calls.append(messages)
        return AiCompletion({"drafts": [], "fits": False, "reason": "These reviews were not forecasts."}, "m:free")

    complete.calls = []
    result = asyncio.run(
        suggest_variants(ORIGINAL, JOB, "Financial forecasting", "Financial Forecasting", "domain",
                         incorporate_keyword=True, complete=complete)
    )
    rule = json.loads(complete.calls[0][1]["content"])["keyword_rule"]
    assert 'must use the phrase "Financial Forecasting"' in rule
    assert result["fits"] is False and result["reason"] == "These reviews were not forecasts."


def test_keyword_mode_is_cached_apart_from_plain_drafts():
    complete = reply("Led budgeting reviews and financial forecasting for regional teams")
    for incorporate in (False, True, True):
        asyncio.run(suggest_variants(ORIGINAL, JOB, "req", "Financial Forecasting", "domain",
                                     incorporate_keyword=incorporate, complete=complete))
    assert len(complete.calls) == 2


def test_guarded_keyword_ignores_keyword_mode():
    complete = reply("Led budgeting reviews for regional teams")
    result = asyncio.run(suggest_variants(ORIGINAL, JOB, "req", "PMP", "credential", incorporate_keyword=True, complete=complete))
    assert "Do not add" in json.loads(complete.calls[0][1]["content"])["keyword_rule"]
    assert [item["body"] for item in result["drafts"]] == ["Led budgeting reviews for regional teams"]
    assert result["fits"] is True


def test_one_line_goal_drops_drafts_over_the_character_budget():
    long_original = "Owned budgeting reviews for regional teams across every quarter and planning cycle this year"
    complete = reply("Owned budgeting reviews for regional teams", "Owned budgeting reviews for regional teams across every quarter")
    result = asyncio.run(
        suggest_variants(long_original, "", "", "", goal="one_line", max_chars=50, placement_id="p1", complete=complete)
    )
    assert [item["body"] for item in result["drafts"]] == ["Owned budgeting reviews for regional teams"]
    assert result["dropped"] == 1
    sent = json.loads(complete.calls[0][1]["content"])
    assert sent["max_chars"] == 50
    assert "one resume line" in sent["goal"]
    # Without a job the draft is still remembered, under an empty job id, for provenance.
    assert issued_draft("p1", "Owned budgeting reviews for regional teams", "") == "m:free"


def test_one_line_budget_is_cached_separately():
    complete = reply("Owned budgeting reviews")
    for limit in (60, 60, 80):
        asyncio.run(suggest_variants(ORIGINAL, "", "", "", goal="one_line", max_chars=limit, complete=complete))
    assert len(complete.calls) == 2


def test_other_goals_ignore_max_chars():
    complete = reply("Led budgeting reviews for regional teams")
    asyncio.run(suggest_variants(ORIGINAL, JOB, "req", "kw", goal="concise", max_chars=30, complete=complete))
    assert "max_chars" not in json.loads(complete.calls[0][1]["content"])
