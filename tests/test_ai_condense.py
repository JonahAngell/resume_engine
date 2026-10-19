import asyncio
import json

import pytest

from app.ai_client import AiCallError, AiCompletion
from app.ai_condense import clear_cache, condense_resume, recommend
from app.ai_variants import clear_cache as clear_variant_cache, issued_draft

JOB = "We need SQL dashboards and stakeholder communication."
LONG = (
    "Built SQL dashboards for the regional sales team that replaced weekly spreadsheet reports and "
    "cut reporting time by 40% across four offices"
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    clear_variant_cache()
    yield
    clear_cache()
    clear_variant_cache()


def bullet(pid, body, parent="p1", index=0, label="Analyst · Acme"):
    return {
        "placement_id": pid,
        "parent_id": parent,
        "section": "work_experience",
        "parent_label": label,
        "body": body,
        "line_id": f"{parent}-bullet-{index}",
    }


BULLETS = [
    bullet("x1", LONG, index=0),
    bullet("x2", "Answered phones", index=1),
    bullet("x3", "Ran the office party", parent="p2", index=0, label="Intern · Old Co"),
]
ENTRIES = [
    {"id": "p1", "section": "work_experience", "label": "Analyst · Acme"},
    {"id": "p2", "section": "work_experience", "label": "Intern · Old Co"},
]
LINES = {"p1-bullet-0": 2, "p1-bullet-1": 1, "p2-bullet-0": 1}


def reply(data, model="m:free"):
    async def complete(messages, schema, name):
        complete.calls.append(messages)
        return AiCompletion(data, model)

    complete.calls = []
    return complete


def run(complete, job=JOB, **kwargs):
    args = {"bullet_lines": LINES, "item_lines": {"p2": 3}, "chars_per_line": 80, "lines_over": 2, "revision": 7}
    return asyncio.run(condense_resume(job, BULLETS, ENTRIES, complete=complete, **{**args, **kwargs}))


def test_valid_suggestions_are_kept_and_unknown_ids_dropped():
    complete = reply(
        {
            "condense": [{"id": "b1", "body": "Built SQL dashboards that cut reporting time by 40%", "reason": "Tighter."}],
            "remove_bullets": [{"id": "b2", "reason": "Weak."}, {"id": "b99", "reason": "?"}],
            "remove_entries": [{"id": "e2", "reason": "Least relevant."}, {"id": "e9"}],
        }
    )
    result = run(complete, job_id="j1")
    assert result["method"] == "ai" and result["revision"] == 7
    kinds = [(item["kind"], item["id"]) for item in result["items"]]
    assert kinds == [("condense", "x1"), ("remove_bullet", "x2"), ("remove_entry", "p2")]
    condensed = result["items"][0]
    assert condensed["lines"] == 2 and condensed["lines_saved"] == 1 and condensed["original"] == LONG
    assert result["items"][2]["lines_saved"] == 3  # measured entry height wins over the estimate
    assert result["dropped"] == 2
    # Lines over is 2: condensing saves 1, then one removal covers the rest.
    assert [item["recommended"] for item in result["items"]] == [True, True, False]
    assert result["recommended_lines_saved"] == 2
    assert issued_draft("x1", condensed["body"], "j1") == "m:free"


def test_sent_request_has_lines_and_trim_hints_but_no_contact_details():
    complete = reply({"condense": [], "remove_bullets": [], "remove_entries": []})
    run(complete, job=JOB + " apply at hr@example.com")
    sent = json.loads(complete.calls[0][1]["content"])
    assert sent["lines_over"] == 2 and sent["chars_per_line"] == 80
    first = sent["bullets"][0]
    assert first["lines"] == 2 and first["trim_to_save_line"] == len(LONG) - 80
    assert "hr@example.com" not in sent["posting"]


@pytest.mark.parametrize(
    "body",
    [
        "Built SQL dashboards that cut reporting time by 55%",  # new number
        "Built Tableau dashboards that cut reporting time by 40%",  # new tool
        LONG,  # saves no line
    ],
)
def test_unsafe_or_useless_condensing_is_dropped(body):
    complete = reply({"condense": [{"id": "b1", "body": body}], "remove_bullets": [], "remove_entries": []})
    result = run(complete)
    assert result["method"] == "heuristic" and result["status"] == "invalid"


def test_bullets_of_a_removed_entry_are_not_listed_twice():
    complete = reply(
        {
            "condense": [],
            "remove_bullets": [{"id": "b3"}],
            "remove_entries": [{"id": "e2"}],
        }
    )
    result = run(complete)
    assert [(item["kind"], item["id"]) for item in result["items"]] == [("remove_entry", "p2")]


@pytest.mark.parametrize("status", ["unavailable", "rate_limited", "invalid"])
def test_failure_falls_back_to_heuristic(status):
    async def complete(messages, schema, name):
        raise AiCallError(status)

    result = run(complete)
    assert result["status"] == status and result["method"] == "heuristic"
    condense = [item for item in result["items"] if item["kind"] == "condense"]
    assert [item["id"] for item in condense] == ["x1"] and condense[0]["body"] == ""
    assert "Cutting about" in condense[0]["reason"]
    # With a job, the role that uses none of its keywords is offered for removal.
    assert ("remove_entry", "p2") in [(item["kind"], item["id"]) for item in result["items"]]


def test_heuristic_without_job_only_lists_wrapping_bullets():
    result = asyncio.run(
        condense_resume("", BULLETS, ENTRIES, LINES, {}, 80, 2, use_ai=False, complete=reply({}))
    )
    assert [(item["kind"], item["id"]) for item in result["items"]] == [("condense", "x1")]
    assert not result["items"][0]["recommended"]


def test_unmeasured_bullets_are_estimated_from_length():
    result = asyncio.run(condense_resume("", BULLETS, ENTRIES, {}, {}, 60, 0, use_ai=False, complete=reply({})))
    assert result["items"][0]["lines"] == 3


def test_cache_hit_skips_the_call():
    complete = reply({"condense": [], "remove_bullets": [{"id": "b2"}], "remove_entries": []})
    run(complete)
    run(complete)
    assert len(complete.calls) == 1


def test_recommend_stops_once_lines_are_covered():
    condensed = [{"body": "x", "lines_saved": 1, "recommended": False} for _ in range(3)]
    removed = [{"lines_saved": 2, "recommended": False}]
    assert recommend(condensed, removed, [], 2) == 2
    assert [item["recommended"] for item in condensed] == [True, True, False]
    assert removed[0]["recommended"] is False
