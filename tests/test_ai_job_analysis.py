"""AI job analysis: quotes are checked against the posting, and AI-found rows count less until accepted."""

import asyncio

from app.ai_client import AiCallError
from app.ai_job_analysis import analyze_job, body_hash, is_current, validate
from app.job_match import AI_PENDING_WEIGHT, analyze_requirements, match_qualifications

POSTING = """Senior Analyst

Requirements:
- Experience with SQL
- Ability to translate complex analysis into clear insights for senior leaders
- Comfortable presenting to executives

Pay Transparency
The hiring range for this position is $100,000 - $120,000 per year.
"""


class Completion:
    def __init__(self, data):
        self.data = data
        self.model = "test-model"


def fake(data):
    async def complete(messages, schema, name):
        # The model sees the posting's layout: headings and bullets on their own lines.
        assert name == "job_analysis" and "Requirements:\n- Experience with SQL\n" in messages[1]["content"]
        return Completion(data)

    return complete


def test_only_quoted_requirements_and_keywords_inside_the_quote_are_kept():
    kept, dropped = validate(
        {
            "requirements": [
                {"source_span": "Experience with SQL", "group": "required", "category": "tool", "keywords": ["SQL", "Python"]},
                {
                    "source_span": "ability to translate complex analysis into clear  insights for senior leaders",
                    "group": "Required",
                    "category": "soft skill",
                    "keywords": ["translate complex analysis into clear insights", "insights for senior leaders"],
                    "match_mode": "any",
                },
                {"source_span": "Expert in Kubernetes", "group": "required", "category": "tool", "keywords": ["Kubernetes"]},
                {"source_span": "The hiring range for this position is $100,000", "group": "required", "category": "domain", "keywords": ["hiring"]},
                {"source_span": "Comfortable presenting to executives", "group": "nice", "category": "made-up", "keywords": ["CEO"]},
            ]
        },
        POSTING,
    )
    assert [item["text"] for item in kept] == [
        "Experience with SQL",
        # The posting's own casing and spacing, so the highlight matches it.
        "Ability to translate complex analysis into clear insights for senior leaders",
    ]
    assert kept[0]["keywords"] == ["SQL"]  # Python is not in the quote
    assert kept[1]["category"] == "soft_skill" and kept[1]["match_mode"] == "any"
    # Invented requirement, pay line, and a keyword-less item are dropped.
    assert dropped == 3


def test_analysis_is_saved_with_the_posting_hash():
    result = asyncio.run(
        analyze_job(POSTING, fake({"requirements": [{"source_span": "Experience with SQL", "group": "required", "category": "tool", "keywords": ["SQL"]}]}))
    )
    assert result["status"] == "ok"
    analysis = result["analysis"]
    assert analysis["body_hash"] == body_hash(POSTING) and analysis["model"] == "test-model"
    assert is_current(analysis, POSTING + "  ")  # whitespace does not count as a change
    assert not is_current(analysis, POSTING + "\n- Experience with Excel")


def test_failures_save_nothing():
    async def limited(messages, schema, name):
        raise AiCallError("rate_limited")

    assert asyncio.run(analyze_job(POSTING, limited)) == {"status": "rate_limited", "detail": "The AI model is rate limited. Try again in a minute.", "analysis": None}
    assert asyncio.run(analyze_job(POSTING, fake({"requirements": [{"source_span": "Invented", "group": "required", "category": "tool", "keywords": ["x"]}]})))["status"] == "invalid"


AI_ROWS = [
    {"text": "Experience with SQL", "group": "required", "category": "tool", "keywords": ["SQL"], "match_mode": "all"},
    {
        "text": "Ability to translate complex analysis into clear insights for senior leaders",
        "group": "required",
        "category": "soft_skill",
        "keywords": ["clear insights for senior leaders"],
        "match_mode": "all",
    },
]


def required_rows(review):
    return {row["text"]: row for row in analyze_requirements(POSTING, review)["required"]}


def test_ai_rows_confirm_rule_rows_and_add_the_missing_ones_at_lower_weight():
    plain = required_rows({})
    assert "Ability to translate complex analysis into clear insights for senior leaders" not in plain

    rows = required_rows({"ai": AI_ROWS})
    sql = rows["Experience with SQL"]
    assert sql["source"] == "rules" and sql["ai_confirmed"] and sql["weight"] == plain["Experience with SQL"]["weight"]
    added = rows["Ability to translate complex analysis into clear insights for senior leaders"]
    assert added["source"] == "ai" and added["ai_pending"]
    assert added["weight"] == 1.0 * AI_PENDING_WEIGHT
    assert added["keywords"] == ["clear insights for senior leaders"]


def test_accepting_gives_full_weight_and_dismissing_removes_it():
    text = AI_ROWS[1]["text"]
    accepted = required_rows({"ai": AI_ROWS, "ai_accepted": [text]})[text]
    assert accepted["weight"] == 1.0 and not accepted["ai_pending"]
    assert text not in required_rows({"ai": AI_ROWS, "dismissed": [text]})


def test_pending_rows_count_in_scores_but_not_in_the_totals():
    resume = {"summary": "Gave senior leaders clear insights from forecasting work."}
    pending = match_qualifications(POSTING, resume, review={"ai": AI_ROWS})
    accepted = match_qualifications(POSTING, resume, review={"ai": AI_ROWS, "ai_accepted": [AI_ROWS[1]["text"]]})
    assert pending["ai_pending_count"] == 1 and accepted["ai_pending_count"] == 0
    assert pending["required_count"] == accepted["required_count"] - 1
    row = next(row for row in pending["required"] if row["source"] == "ai")
    assert row["matched"] and row["keywords"][0]["relation"] == "phrase"
    # Matched at half weight while pending, so accepting it raises coverage.
    assert 0 < pending["scores"]["required_coverage"] < accepted["scores"]["required_coverage"]
