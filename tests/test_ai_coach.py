import asyncio

import pytest

from app.ai_client import AiCallError, AiCompletion
from app.ai_coach import MAX_SUGGESTIONS, clear_cache, coach_resume
from app.ai_variants import clear_cache as clear_variant_cache, issued_draft

DESCRIPTION = """Senior Product Analyst

Required Qualifications
- Experience with Kubernetes and Terraform
- Experience with financial forecasting for budgeting teams

Preferred Qualifications
- Experience with Looker
"""
RESUME = {
    "summary": "Analyst who turns crew schedules into decisions operations teams can use.",
    "tool_groups": [{"name": "Platforms", "items": ["Snowflake"]}],
}
PLACED = [
    {"id": "b1", "placement_id": "p1", "parent_id": "job-1", "line_index": 0,
     "wording": "Owned budgeting reviews for regional teams", "section": "Work Experience", "tags": []},
    {"id": "b2", "placement_id": "p2", "parent_id": "job-1", "line_index": 1,
     "wording": "Built Looker dashboards for account managers", "section": "Work Experience", "tags": []},
]
FORECAST = "Experience with financial forecasting for budgeting teams"
K8S = "Experience with Kubernetes and Terraform"


@pytest.fixture(autouse=True)
def _fresh():
    clear_cache()
    clear_variant_cache()
    yield
    clear_cache()
    clear_variant_cache()


def model(data):
    async def complete(messages, schema, name):
        complete.calls.append(messages)
        return AiCompletion(data, "m:free")

    complete.calls = []
    return complete


def run(complete, **kwargs):
    return asyncio.run(coach_resume(DESCRIPTION, RESUME, PLACED, {}, 7, job_id="j1", complete=complete, **kwargs))


def test_keeps_checked_cards_and_drops_unsafe_ones():
    complete = model(
        {
            "suggestions": [
                {"kind": "rewrite", "bullet": 1, "requirement": FORECAST, "keyword": "Financial Forecasting",
                 "proposed": "Owned budgeting reviews and financial forecasting for regional teams", "rationale": "Uses the job's words.", "priority": "high"},
                {"kind": "rewrite", "bullet": 9, "requirement": FORECAST, "proposed": "x y z", "priority": "high"},
                {"kind": "rewrite", "bullet": 1, "requirement": FORECAST, "proposed": "Owned budgeting reviews for 12 regional teams"},
                {"kind": "add_skill", "bullet": None, "requirement": K8S, "keyword": "Kubernetes", "priority": "high"},
                {"kind": "add_skill", "bullet": None, "requirement": FORECAST, "keyword": "Financial Forecasting"},
                {"kind": "summary", "bullet": None, "requirement": FORECAST,
                 "proposed": "Analyst who turns crew schedules into forecasting decisions operations teams can use.", "priority": "low"},
                {"kind": "rewrite", "bullet": 1, "requirement": "Not a real requirement", "proposed": "Owned reviews"},
            ],
            "equivalents": [
                {"requirement": FORECAST, "bullet": 1, "rationale": "Budgeting reviews are forecasting work."},
                {"requirement": FORECAST, "bullet": 99, "rationale": "bad index"},
            ],
        }
    )
    result = run(complete)
    assert result["status"] == "ok" and result["revision"] == 7
    kinds = [(card["kind"], card["keyword"]) for card in result["suggestions"]]
    assert ("rewrite", "Financial Forecasting") in kinds
    assert ("add_skill", "Kubernetes") in kinds
    assert ("summary", "Financial Forecasting") in kinds
    assert len(result["suggestions"]) == 3
    assert result["dropped"] == 5
    rewrite = next(card for card in result["suggestions"] if card["kind"] == "rewrite")
    assert rewrite["placement_id"] == "p1" and rewrite["original"] == PLACED[0]["wording"]
    assert result["equivalents"][0]["placement_id"] == "p1"
    # Required items come first, high priority first within a group.
    assert [card["group"] for card in result["suggestions"]] == ["required"] * 3
    assert result["suggestions"][-1]["priority"] == "low"


def test_accepted_rewrite_is_registered_as_issued():
    proposed = "Owned budgeting reviews and financial forecasting for regional teams"
    run(model({"suggestions": [{"kind": "rewrite", "bullet": 1, "requirement": FORECAST, "proposed": proposed}], "equivalents": []}))
    assert issued_draft("p1", proposed, "j1") == "m:free"


def test_cap_and_cache():
    many = [
        {"kind": "rewrite", "bullet": 1, "requirement": FORECAST, "proposed": f"Owned budgeting reviews for regional teams, variant {word}"}
        for word in "abcdefghijklmnopq"
    ]
    complete = model({"suggestions": many, "equivalents": []})
    first = run(complete)
    second = run(complete)
    assert len(first["suggestions"]) == MAX_SUGGESTIONS
    assert first == second and len(complete.calls) == 1


def test_bullets_are_numbered_and_contact_details_removed():
    placed = [{**PLACED[0], "wording": PLACED[0]["wording"] + " me@example.com"}]
    complete = model({"suggestions": [], "equivalents": []})
    asyncio.run(coach_resume(DESCRIPTION, RESUME, placed, {}, 1, complete=complete))
    sent = complete.calls[0][1]["content"]
    assert '"number": 1' in sent and "me@example.com" not in sent


@pytest.mark.parametrize("status", ["unavailable", "rate_limited", "invalid"])
def test_failure_statuses(status):
    async def complete(messages, schema, name):
        raise AiCallError(status)

    result = run(complete)
    assert result["status"] == status and result["suggestions"] == [] and "unchanged" in result["detail"]


def test_missing_key_is_unavailable(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    assert asyncio.run(coach_resume(DESCRIPTION, RESUME, PLACED, {}, 1))["status"] == "unavailable"
