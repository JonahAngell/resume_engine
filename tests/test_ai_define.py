import asyncio

import pytest

from app.ai_client import AiCallError, AiCompletion
from app.ai_define import clear_cache, define_keyword

JOB = "Data Engineer. Required: experience with dbt models. Contact hiring@example.com."


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield
    clear_cache()


def reply(data, model="m:free"):
    async def complete(messages, schema, name):
        complete.calls.append(messages)
        return AiCompletion(data, model)

    complete.calls = []
    return complete


def run(complete, keyword="dbt"):
    return asyncio.run(define_keyword(JOB, keyword, "Experience with dbt models", complete=complete))


def test_definition_is_clipped_and_cached():
    complete = reply({"definition": "A tool " + "x" * 600, "in_this_job": "You would build SQL models."})
    first = run(complete)
    assert first["status"] == "ok"
    assert first["definition"].startswith("A tool") and len(first["definition"]) == 400
    assert first["in_this_job"] == "You would build SQL models."
    assert first["model"] == "m:free"
    second = run(complete)
    assert second == first
    assert len(complete.calls) == 1


def test_only_the_posting_is_sent():
    complete = reply({"definition": "A tool.", "in_this_job": ""})
    run(complete)
    sent = complete.calls[0][1]["content"]
    assert "dbt" in sent
    assert "hiring@example.com" not in sent


def test_empty_definition_is_invalid():
    assert run(reply({"definition": "  "}))["status"] == "invalid"


@pytest.mark.parametrize("status", ["unavailable", "rate_limited", "invalid"])
def test_failure_statuses(status):
    async def complete(messages, schema, name):
        raise AiCallError(status)

    result = run(complete)
    assert result["status"] == status
    assert result["definition"] == ""
    assert result["detail"]
