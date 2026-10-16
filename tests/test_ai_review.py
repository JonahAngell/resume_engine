import json
from uuid import uuid4

import httpx

from app.ai_client import AiCallError, AiCompletion, complete_json
from app.ai_review import clear_cache, redact_resume, review_resume
from app.job_match import match_qualifications
from async_test_utils import run_async

JOB = "Required Qualifications\nDemonstrated experience with Python\n"
RESUME = {
    "header": {
        "name": "Casey Example",
        "email": "casey@example.com",
        "phone": "555-014-2298",
        "linkedin_url": "https://linkedin.com/in/casey-example",
    },
    "summary": "Casey Example builds platforms in Austin. Call 555-014-2298.",
    "tool_groups": [{"name": "Languages", "items": ["SQL"], "bullets": []}],
    "work_experience": [
        {
            "organization": "Analytical Engines",
            "location": "Austin, TX",
            "title": "Engineer",
            "bullets": ["Shipped SQL pipelines for pricing"],
        }
    ],
}
COMPOSITION_ID = uuid4()
SECRETS = (
    "Casey Example",
    "casey@example.com",
    "555-014-2298",
    "https://linkedin.com/in/casey-example",
    "Austin",
)


def setup_function():
    clear_cache()


def _requirement() -> str:
    match = match_qualifications(JOB, RESUME)
    assert match["required_count"] == 1
    assert match["required_matched"] == 0
    return match["required"][0]["text"]


def test_redaction_removes_contact_details():
    redacted = redact_resume(RESUME)
    encoded = json.dumps(redacted)
    for secret in SECRETS:
        assert secret.casefold() not in encoded.casefold()
    assert "Analytical Engines" not in encoded
    assert "Shipped SQL pipelines for pricing" in encoded
    assert "SQL" in redacted["skills"]


def test_review_drops_ungrounded_items_and_keeps_the_score():
    requirement = _requirement()
    sent = []

    async def complete(messages, schema, name):
        sent.append({"name": name, "messages": messages})
        if name == "job_review":
            return AiCompletion(
                data={
                    "families": [
                        {"label": "Data engineering", "confidence": 0.8},
                        {"label": "Unclear", "confidence": 0.1},
                    ],
                    "requirements": [
                        {
                            "text": requirement,
                            "group": "required",
                            "category": "tool",
                            "source_span": requirement,
                        },
                        {
                            "text": "Advanced Excel",
                            "group": "required",
                            "category": "tool",
                            "source_span": "advanced Excel",
                        },
                        {
                            "text": requirement,
                            "group": "required",
                            "category": "vibes",
                            "source_span": requirement,
                        },
                    ],
                    "keywords": [
                        {"keyword": "Python", "category": "tool", "source_span": requirement},
                        {"keyword": "Excel", "category": "tool", "source_span": "advanced Excel"},
                    ],
                },
                model="openrouter/free",
            )
        return AiCompletion(
            data={
                "semantic_candidates": [
                    {
                        "requirement": requirement,
                        "resume_span": "Shipped SQL pipelines for pricing",
                        "section": "Work Experience",
                        "confidence": 0.82,
                        "rationale": "The bullet shows data tooling work.",
                    },
                    {
                        "requirement": requirement,
                        "resume_span": "Shipped SQL pipelines for pricing",
                        "section": "Work Experience",
                        "confidence": 0.2,
                        "rationale": "Too weak to keep.",
                    },
                ],
                "bullet_tags": [
                    {
                        "bullet": "Shipped SQL pipelines for pricing",
                        "action": "Shipped",
                        "tool": "SQL",
                        "outcome": "pricing",
                    }
                ],
                "suggestions": [
                    {
                        "requirement": requirement,
                        "resume_quote": "Shipped SQL pipelines for pricing",
                        "suggestion": "Keep this bullet only where the pricing work is true.",
                    },
                    {
                        "requirement": requirement,
                        "resume_quote": "managed a team of forty",
                        "suggestion": "Invented leadership.",
                    },
                ],
            },
            model="openrouter/free",
        )

    result = run_async(
        review_resume(COMPOSITION_ID, JOB, RESUME, complete=complete)
    )
    assert result["status"] == "ok"
    assert result["match"]["required_matched"] == 0
    assert result["match"]["required_count"] == 1
    assert [item["label"] for item in result["families"]] == ["Data engineering"]
    assert [item["category"] for item in result["requirements"]] == ["tool"]
    assert result["requirements"][0]["text"] == requirement
    assert [item["keyword"] for item in result["keywords"]] == ["Python"]
    assert len(result["semantic_candidates"]) == 1
    assert result["semantic_candidates"][0]["resume_span"] == "Shipped SQL pipelines for pricing"
    assert len(result["suggestions"]) == 1
    assert result["bullet_tags"][0]["tool"] == "SQL"
    compare = next(item for item in sent if item["name"] == "resume_comparison")
    body = json.dumps(compare["messages"])
    for secret in SECRETS:
        assert secret.casefold() not in body.casefold()


def test_repeated_review_uses_the_cache():
    requirement = _requirement()
    calls = {"n": 0}

    async def complete(messages, schema, name):
        calls["n"] += 1
        if name == "job_review":
            return AiCompletion(
                data={
                    "families": [],
                    "requirements": [
                        {
                            "text": requirement,
                            "group": "required",
                            "category": "tool",
                            "source_span": requirement,
                        }
                    ],
                    "keywords": [],
                },
                model="openrouter/free",
            )
        return AiCompletion(
            data={"semantic_candidates": [], "bullet_tags": [], "suggestions": []},
            model="openrouter/free",
        )

    first = run_async(review_resume(COMPOSITION_ID, JOB, RESUME, complete=complete))
    second = run_async(review_resume(COMPOSITION_ID, JOB, RESUME, complete=complete))
    assert first["status"] == "ok"
    assert second["requirements"] == first["requirements"]
    assert calls["n"] == 2


def test_comparison_failure_keeps_job_categories_and_the_score():
    requirement = _requirement()

    async def complete(messages, schema, name):
        if name == "resume_comparison":
            raise AiCallError("rate_limited")
        return AiCompletion(
            data={
                "families": [{"label": "Data engineering", "confidence": 0.7}],
                "requirements": [
                    {
                        "text": requirement,
                        "group": "required",
                        "category": "tool",
                        "source_span": requirement,
                    }
                ],
                "keywords": [],
            },
            model="openrouter/free",
        )

    result = run_async(review_resume(COMPOSITION_ID, JOB, RESUME, complete=complete))
    assert result["status"] == "ok"
    assert result["match"]["required_matched"] == 0
    assert result["requirements"][0]["category"] == "tool"
    assert result["semantic_candidates"] == []


def test_rate_limit_returns_the_deterministic_match():
    async def complete(messages, schema, name):
        raise AiCallError("rate_limited")

    result = run_async(review_resume(COMPOSITION_ID, JOB, RESUME, complete=complete))
    assert result["status"] == "rate_limited"
    assert result["match"]["required_count"] == 1
    assert result["match"]["required_matched"] == 0
    assert result["semantic_candidates"] == []
    assert "unchanged" in result["detail"]


def test_invalid_model_json_returns_the_deterministic_match():
    async def complete(messages, schema, name):
        raise AiCallError("invalid")

    result = run_async(review_resume(COMPOSITION_ID, JOB, RESUME, complete=complete))
    assert result["status"] == "invalid"
    assert result["match"]["required_matched"] == 0
    assert result["requirements"] == []


def _client(monkeypatch, handler):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")
    transport = httpx.MockTransport(handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await complete_json(
                [{"role": "user", "content": "Review this posting."}],
                {"type": "object"},
                "job_review",
                client=client,
            )

    return run


def test_client_retries_a_rate_limit_once(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "slow"})
        return httpx.Response(
            200,
            json={
                "model": "meta/example:free",
                "choices": [{"message": {"content": '{"families": []}'}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3},
            },
        )

    result = run_async(_client(monkeypatch, handler)())
    assert calls["n"] == 2
    assert result.data == {"families": []}
    assert result.model == "meta/example:free"


def test_client_repairs_invalid_json_once(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        content = "Here is the review." if calls["n"] == 1 else '{"families": []}'
        return httpx.Response(
            200,
            json={"model": "openrouter/free", "choices": [{"message": {"content": content}}]},
        )

    result = run_async(_client(monkeypatch, handler)())
    assert calls["n"] == 2
    assert result.data == {"families": []}


def test_client_invalid_after_a_failed_repair(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={"model": "openrouter/free", "choices": [{"message": {"content": "still not json"}}]},
        )

    try:
        run_async(_client(monkeypatch, handler)())
    except AiCallError as exc:
        assert exc.status == "invalid"
    else:
        raise AssertionError("expected invalid JSON")
    assert calls["n"] == 2


def test_client_stops_after_a_second_rate_limit(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "slow"})

    try:
        run_async(_client(monkeypatch, handler)())
    except AiCallError as exc:
        assert exc.status == "rate_limited"
    else:
        raise AssertionError("expected rate limit")
    assert calls["n"] == 2


def test_client_rejects_a_paid_model_without_calling(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("paid model was called")

    transport = httpx.MockTransport(handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await complete_json(
                [{"role": "user", "content": "Review this posting."}],
                {"type": "object"},
                "job_review",
                client=client,
            )

    try:
        run_async(run())
    except AiCallError as exc:
        assert exc.status == "unavailable"
    else:
        raise AssertionError("expected unavailable")


def test_client_is_unavailable_without_a_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("missing key was called")

    transport = httpx.MockTransport(handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await complete_json(
                [{"role": "user", "content": "Review this posting."}],
                {"type": "object"},
                "job_review",
                client=client,
            )

    try:
        run_async(run())
    except AiCallError as exc:
        assert exc.status == "unavailable"
    else:
        raise AssertionError("expected unavailable")
