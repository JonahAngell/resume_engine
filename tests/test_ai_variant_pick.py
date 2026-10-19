import asyncio

import pytest

from app.ai_client import AiCallError, AiCompletion
from app.ai_variant_pick import build_slots, clear_cache, pick_variants

JOB = "We need SQL dashboards and stakeholder communication. Experience with forecasting."


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield
    clear_cache()


def placement(pid, bullet, variant, parent="p1", body="Did general work"):
    return {
        "placement_id": pid,
        "bullet_id": bullet,
        "variant_id": variant,
        "parent_id": parent,
        "section": "work_experience",
        "parent_label": "Analyst · Acme",
        "body": body,
        "variant_name": "Default",
    }


def option(bullet, variant, body, parent="p1", name="Alt"):
    return {"bullet_id": bullet, "variant_id": variant, "parent_id": parent, "name": name, "body": body}


LIBRARY = [
    option("b1", "v1", "Did general work", name="Default"),
    option("b1", "v2", "Built SQL dashboards for forecasting", name="Data"),
    option("b2", "v3", "Placed elsewhere on this resume"),
    option("b3", "v4", "Led stakeholder communication for launches"),
    option("b9", "v9", "Other role SQL dashboards", parent="p2"),
]


def scores(mapping, model="m:free"):
    async def complete(messages, schema, name):
        complete.calls.append(messages)
        return AiCompletion(mapping, model)

    complete.calls = []
    return complete


def test_candidates_are_same_parent_and_skip_bullets_placed_elsewhere():
    slots = build_slots([placement("x", "b1", "v1")], LIBRARY, ["SQL"], placed_ids=["b1", "b2"])
    bodies = [item["body"] for item in slots[0]["candidates"]]
    assert bodies[0] == "Did general work"
    assert "Placed elsewhere on this resume" not in bodies
    assert "Other role SQL dashboards" not in bodies
    assert set(bodies) == {"Did general work", "Built SQL dashboards for forecasting", "Led stakeholder communication for launches"}


def test_keyword_ranking_recommends_a_variant_with_more_job_keywords(monkeypatch):
    monkeypatch.setattr("app.ai_variant_pick.ai_available", lambda: False)
    result = asyncio.run(pick_variants(JOB, [placement("x", "b1", "v1")], LIBRARY, revision=3))
    slot = result["slots"][0]
    assert result["status"] == "unavailable" and result["method"] == "keywords"
    best = next(item for item in slot["candidates"] if item["key"] == slot["best_key"])
    assert slot["recommend"] and best["variant_id"] == "v2"
    assert result["revision"] == 3


def test_ai_scores_rank_and_require_a_margin():
    slots = build_slots([placement("x", "b1", "v1")], LIBRARY, [])
    keys = {item["body"]: item["key"] for item in slots[0]["candidates"]}
    reply = scores(
        {
            "slots": [
                {
                    "id": "s1",
                    "scores": [
                        {"key": keys["Did general work"], "score": 60, "reason": "Vague."},
                        {"key": keys["Built SQL dashboards for forecasting"], "score": 64, "reason": "Close."},
                        {"key": keys["Led stakeholder communication for launches"], "score": 90, "reason": "Direct."},
                        {"key": "c99", "score": 100},
                    ],
                }
            ]
        }
    )
    result = asyncio.run(pick_variants(JOB, [placement("x", "b1", "v1")], LIBRARY, complete=reply))
    slot = result["slots"][0]
    assert result["method"] == "ai" and result["dropped"] == 1
    assert slot["candidates"][0]["body"] == "Led stakeholder communication for launches"
    assert slot["candidates"][0]["reason"] == "Direct."
    assert slot["recommend"] and slot["best_key"] == slot["candidates"][0]["key"]


def test_small_ai_gain_keeps_current():
    reply = scores({"slots": [{"id": "s1", "scores": [{"key": "c1", "score": 80}, {"key": "c2", "score": 84}]}]})
    library = [option("b1", "v1", "Did general work"), option("b1", "v2", "Did general work well")]
    result = asyncio.run(pick_variants(JOB, [placement("x", "b1", "v1")], library, complete=reply))
    slot = result["slots"][0]
    assert not slot["recommend"] and slot["best_key"] == slot["current_key"]


def test_one_unused_bullet_is_not_picked_for_two_slots():
    library = [
        option("b1", "v1", "First bullet"),
        option("b2", "v2", "Second bullet"),
        option("b3", "v3", "Great new bullet"),
    ]
    rows = [placement("x", "b1", "v1", body="First bullet"), placement("y", "b2", "v2", body="Second bullet")]
    reply = scores(
        {
            "slots": [
                {"id": "s1", "scores": [{"key": "c1", "score": 10}, {"key": "c2", "score": 95}]},
                {"id": "s2", "scores": [{"key": "c1", "score": 10}, {"key": "c2", "score": 95}]},
            ]
        }
    )
    result = asyncio.run(pick_variants(JOB, rows, library, complete=reply))
    picks = [
        next(item for item in slot["candidates"] if item["key"] == slot["best_key"])["bullet_id"]
        for slot in result["slots"]
    ]
    assert picks == ["b3", "b2"]


def test_model_failure_falls_back_to_keywords():
    async def broken(messages, schema, name):
        raise AiCallError("rate_limited")

    result = asyncio.run(pick_variants(JOB, [placement("x", "b1", "v1")], LIBRARY, complete=broken))
    assert result["status"] == "rate_limited" and result["method"] == "keywords"
    assert result["slots"][0]["recommend"]


def test_request_does_not_send_resume_contact_details():
    reply = scores({"slots": []})
    library = [option("b1", "v1", "Did general work"), option("b1", "v2", "Emailed jo@example.com weekly")]
    asyncio.run(pick_variants(JOB, [placement("x", "b1", "v1")], library, complete=reply))
    assert "jo@example.com" not in reply.calls[0][1]["content"]
