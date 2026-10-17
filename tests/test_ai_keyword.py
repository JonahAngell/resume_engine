import asyncio
import json

import pytest

from app.ai_client import AiCallError, AiCompletion
from app.ai_keyword import assist_keyword, clear_cache, filter_keyword, new_bullet_key, resume_entries
from app.ai_variants import clear_cache as clear_variant_cache
from app.ai_variants import issued_draft

JOB = "Product Analyst. Required: A/B testing of product changes. Tools: Optimizely, Amplitude."
RESUME = {
    "work_experience": [
        {"id": "e1", "organization": "Fieldnote", "title": "Product Analyst", "date": "2024", "bullets": []},
        {"id": "e2", "organization": "Harborlight", "title": "Data Analyst", "date": "2021", "bullets": []},
    ],
    "projects": [{"id": "p1", "name": "Cue Ledger", "subtitle": "Python", "bullets": []}],
    "leadership": [{"organization": "No id", "title": "Lead"}],
}
PLACED = [
    {"placement_id": "b1", "parent_id": "e1", "line_index": 0, "section": "Work Experience", "tags": [],
     "wording": "Tested two onboarding flows with account managers to lift renewals 12%"},
    {"placement_id": "b2", "parent_id": "e2", "line_index": 0, "section": "Work Experience", "tags": [],
     "wording": "Modeled attendance and staffing for 14 venues"},
    {"placement_id": "b3", "parent_id": "edu", "line_index": 0, "section": "Education", "tags": [],
     "wording": "Thesis on survey sampling"},
]


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    clear_variant_cache()
    yield
    clear_cache()
    clear_variant_cache()


def reply(revisions=(), new_bullets=(), reason="", model="m:free"):
    async def complete(messages, schema, name):
        complete.calls.append(messages)
        return AiCompletion(
            {"revisions": list(revisions), "new_bullets": list(new_bullets), "no_fit_reason": reason}, model
        )

    complete.calls = []
    return complete


def run(complete, keyword="A/B Testing", category="methodology", **kw):
    return asyncio.run(
        assist_keyword(JOB, RESUME, PLACED, keyword, "A/B testing of product changes", category, 7,
                       job_id="j1", complete=complete, **kw)
    )


def test_entries_and_bullets_are_numbered_in_resume_order():
    entries, bullets = resume_entries(RESUME, PLACED)
    assert [item["entry"] for item in entries] == ["Product Analyst, Fieldnote", "Data Analyst, Harborlight", "Cue Ledger, Python"]
    assert [item["entry_number"] for item in bullets] == [1, 2, None]
    assert entries[0]["bullets"] == [PLACED[0]["wording"]]


def test_prompt_lists_entries_bullets_and_likely_fits():
    complete = reply()
    run(complete)
    sent = json.loads(complete.calls[0][1]["content"])
    assert sent["keyword"] == "A/B Testing"
    assert [item["number"] for item in sent["entries"]] == [1, 2, 3]
    assert [item["entry"] for item in sent["bullets"]] == [1, 2, None]


def test_bullets_sharing_requirement_words_are_marked_likely_fit():
    complete = reply()
    asyncio.run(assist_keyword(JOB, RESUME, PLACED, "A/B Testing", "A/B testing of onboarding flows", "methodology", 1,
                               complete=complete))
    sent = json.loads(complete.calls[0][1]["content"])
    assert [item["number"] for item in sent["bullets"] if item.get("likely_fit")] == [1]


def test_safe_revisions_and_new_bullets_are_kept_and_remembered():
    revision = "Ran A/B testing on two onboarding flows with account managers to lift renewals 12%"
    fresh = "Designed A/B testing plans for product changes, reaching [X%] lift"
    result = run(reply(
        revisions=[{"bullet": 1, "body": revision, "rationale": "Names the method."}],
        new_bullets=[{"entry": 1, "body": fresh, "rationale": "New evidence."}],
    ))
    assert result["status"] == "ok" and result["revision"] == 7
    assert [card["body"] for card in result["revisions"]] == [revision]
    assert result["revisions"][0]["placement_id"] == "b1"
    assert result["revisions"][0]["original"] == PLACED[0]["wording"]
    card = result["new_bullets"][0]
    assert (card["parent_id"], card["section"], card["placeholders"]) == ("e1", "work_experience", True)
    assert [item["parent_id"] for item in result["entries"]] == ["e1", "e2", "p1"]
    assert issued_draft("b1", revision, "j1") == "m:free"
    assert issued_draft(new_bullet_key("e1"), fresh, "j1") == "m:free"
    assert issued_draft(new_bullet_key("e2"), fresh, "j1") is None


@pytest.mark.parametrize(
    "item",
    [
        {"bullet": 2, "body": "Modeled attendance and staffing for 14 venues"},  # no keyword
        {"bullet": 2, "body": "Used A/B testing to model attendance and staffing for 20 venues"},  # new number
        {"bullet": 2, "body": "Used A/B testing in Optimizely to model attendance for 14 venues"},  # job tool
        {"bullet": 2, "body": "Used A/B testing at Contoso to model attendance for 14 venues"},  # proper noun
        {"bullet": 2, "body": "Used A/B testing to model attendance for [N] venues"},  # placeholder in a revision
        {"bullet": 9, "body": "Used A/B testing to model attendance for 14 venues"},  # unknown bullet
        {"bullet": "2", "body": "Used A/B testing to model attendance for 14 venues"},  # not a number
    ],
)
def test_unsafe_revisions_are_dropped(item):
    entries, bullets = resume_entries(RESUME, PLACED)
    part = filter_keyword({"revisions": [item], "new_bullets": []}, entries, bullets, "A/B Testing", "methodology", ["Optimizely", "Amplitude"])
    assert part["revisions"] == [] and part["dropped"] == 1


@pytest.mark.parametrize(
    "item",
    [
        {"entry": 2, "body": "Planned staffing models for venues"},  # no keyword
        {"entry": 2, "body": "Ran A/B testing on staffing for 30 venues"},  # number the entry lacks
        {"entry": 2, "body": "Ran A/B testing on staffing in Amplitude"},  # job tool
        {"entry": 2, "body": "Ran A/B testing on staffing with Contoso"},  # proper noun
        {"entry": 4, "body": "Ran A/B testing on staffing"},  # entry without an id is not offered
        {"entry": 2, "body": "Modeled attendance and staffing for 14 venues"},  # copies a bullet
    ],
)
def test_unsafe_new_bullets_are_dropped(item):
    entries, bullets = resume_entries(RESUME, PLACED)
    part = filter_keyword({"revisions": [], "new_bullets": [item]}, entries, bullets, "A/B Testing", "methodology", ["Optimizely", "Amplitude"])
    assert part["new_bullets"] == [] and part["dropped"] == 1


def test_new_bullet_may_reuse_its_entry_facts_and_placeholders():
    entries, bullets = resume_entries(RESUME, PLACED)
    part = filter_keyword(
        {"revisions": [], "new_bullets": [
            {"entry": 2, "body": "Ran A/B testing on staffing plans across 14 venues"},
            {"entry": 2, "body": "Used A/B testing to compare [N] staffing schedules, saving [X hours]"},
        ]},
        entries, bullets, "A/B Testing", "methodology", [],
    )
    assert [card["placeholders"] for card in part["new_bullets"]] == [False, True]


def test_caps_and_one_revision_per_bullet():
    entries, bullets = resume_entries(RESUME, PLACED)
    revisions = [{"bullet": 1, "body": f"Ran A/B testing on two onboarding flows {word} to lift renewals 12%"} for word in "abcd"]
    revisions += [{"bullet": 2, "body": "Used A/B testing to model attendance and staffing for 14 venues"}]
    fresh = [{"entry": 3, "body": f"Applied A/B testing to log layouts, round {word}"} for word in "abc"]
    part = filter_keyword({"revisions": revisions, "new_bullets": fresh}, entries, bullets, "A/B Testing", "methodology", [])
    assert [card["placement_id"] for card in part["revisions"]] == ["b1", "b2"]
    assert len(part["new_bullets"]) == 2


def test_no_fit_reason_is_passed_through_only_when_nothing_is_kept():
    result = run(reply(reason="Nothing here describes experiments."))
    assert result["no_fit_reason"] == "Nothing here describes experiments."
    result = run(reply(
        revisions=[{"bullet": 1, "body": "Ran A/B testing on two onboarding flows with account managers to lift renewals 12%"}],
        reason="ignored",
    ), keyword="A/B Testing", category="domain")
    assert result["no_fit_reason"] == ""


def test_guarded_keyword_never_calls_the_model():
    complete = reply()
    result = run(complete, keyword="Optimizely", category="tool")
    assert complete.calls == [] and result["allowed"] is False
    assert result["revisions"] == [] and result["new_bullets"] == []


def test_cache_hit_skips_the_call_and_remembers_again():
    body = "Ran A/B testing on two onboarding flows with account managers to lift renewals 12%"
    complete = reply(revisions=[{"bullet": 1, "body": body}])
    run(complete)
    clear_variant_cache()
    run(complete)
    assert len(complete.calls) == 1
    assert issued_draft("b1", body, "j1") == "m:free"


@pytest.mark.parametrize("status", ["unavailable", "rate_limited", "invalid"])
def test_each_failure_status_is_returned(status):
    async def complete(messages, schema, name):
        raise AiCallError(status)

    result = run(complete)
    assert result["status"] == status and "unchanged" in result["detail"]
    assert len(result["entries"]) == 3


def test_missing_key_is_unavailable(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    result = asyncio.run(assist_keyword(JOB, RESUME, PLACED, "A/B Testing", "", "methodology", 1))
    assert result["status"] == "unavailable"
