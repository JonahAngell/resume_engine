import json

from app.ats_score import DISCLAIMER, METHODOLOGY, WEIGHTS, score_resume

RESUME = {
    "header": {"name": "N", "email": "n@example.com", "phone": "555-0100"},
    "work_experience": [
        {
            "title": "Senior Product Analyst",
            "date": "2021 – Present",
            "bullets": [
                "Built a Looker dashboard used by 40 account managers to track renewal risk.",
                "Owned weekly reliability reviews for the logger fleet with firmware and support.",
            ],
        }
    ],
    "education": [{"institution": "U", "degree": "BFA"}],
    "tool_groups": [{"name": "Platforms", "items": ["Looker", "SQL"]}],
}


def kw(name, found, where=""):
    return {"keyword": name, "found": found, "where": where}


MATCH = {
    "required": [
        {"text": "SQL and Looker", "matched": True, "keywords": [kw("SQL", True, "Skills"), kw("Looker", True, "Work Experience")]},
        {"text": "Kubernetes", "matched": False, "keywords": [kw("Kubernetes", False)]},
    ],
    "preferred": [{"text": "Tableau", "matched": False, "keywords": [kw("Tableau", False)]}],
    "scores": {"required_coverage": 0.5},
    "eligibility": {"degree": {"status": "pass"}, "years": {"status": "unknown"}},
}
JOB = {"role": "Senior Product Analyst", "title": "Parkline — Senior Product Analyst"}
COMP = {"display_title": "", "target_role": "", "template_style": "classic"}


def component(result, cid):
    return next(item for item in result["components"] if item["id"] == cid)


def test_weights_sum_to_100_and_methodology_and_disclaimer_are_returned():
    assert sum(WEIGHTS.values()) == 100
    result = score_resume(MATCH, RESUME, JOB, COMP, 1)
    assert [item["id"] for item in result["methodology"]] == [item["id"] for item in METHODOLOGY]
    assert result["disclaimer"] == DISCLAIMER and "not a guarantee" in DISCLAIMER
    assert result["score"] == round(sum(item["earned"] for item in result["components"]))
    assert result["band"] in {"Strong", "Fair", "Needs work"}


def test_keyword_match_weights_required_twice():
    # Found: SQL(2) + Looker(2) = 4 of 2+2+2+1 = 7
    keywords = component(score_resume(MATCH, RESUME, JOB, COMP, 1), "keywords")
    assert keywords["ratio"] == round(4 / 7, 3)
    assert "Kubernetes" in keywords["tips"][0]


def test_required_qualifications_mix_coverage_and_gates():
    requirements = component(score_resume(MATCH, RESUME, JOB, COMP, 1), "requirements")
    assert requirements["ratio"] == round(0.5 * 0.6 + 0.75 * 0.4, 3)


def test_title_uses_most_recent_role():
    title = component(score_resume(MATCH, RESUME, JOB, COMP, 1), "title")
    assert title["ratio"] == 1.0
    other = component(score_resume(MATCH, {**RESUME, "work_experience": []}, JOB, COMP, 1), "title")
    assert other["ratio"] == 0.0 and other["tips"]


def test_keyword_context_counts_bullet_evidence():
    context = component(score_resume(MATCH, RESUME, JOB, COMP, 1), "context")
    assert context["ratio"] == 0.5


def test_parsing_checks_and_table_template_penalty():
    clean = component(score_resume(MATCH, RESUME, JOB, COMP, 1), "parsing")
    assert clean["ratio"] == 1.0
    table = component(score_resume(MATCH, RESUME, JOB, {**COMP, "template_style": "sre"}, 1), "parsing")
    assert table["earned"] == clean["earned"] - 5
    bare = component(score_resume(MATCH, {"work_experience": [{"title": "x", "bullets": []}]}, JOB, COMP, 1), "parsing")
    assert bare["ratio"] < 0.5 and any("email" in tip for tip in bare["tips"])


def test_length_penalizes_long_resumes_and_unquantified_bullets():
    one = component(score_resume(MATCH, RESUME, JOB, COMP, 1), "length")
    four = component(score_resume(MATCH, RESUME, JOB, COMP, 4), "length")
    assert four["earned"] < one["earned"]
    assert any("two pages" in tip for tip in four["tips"])


def test_same_inputs_same_score():
    assert score_resume(MATCH, RESUME, JOB, COMP, 1) == score_resume(MATCH, RESUME, JOB, COMP, 1)


def test_skipped_keywords_still_count_as_missing_but_leave_the_tip():
    skipped = json.loads(json.dumps(MATCH))
    skipped["required"][1]["keywords"][0]["skipped"] = True
    plain = score_resume(MATCH, RESUME, JOB, COMP, 1)
    result = score_resume(skipped, RESUME, JOB, COMP, 1)
    assert result["score"] == plain["score"]
    keywords = component(result, "keywords")
    assert keywords["ratio"] == round(4 / 7, 3)
    assert not any("Kubernetes" in tip for tip in keywords["tips"])
    assert any("1 keyword you marked as not your experience" in tip for tip in keywords["tips"])
