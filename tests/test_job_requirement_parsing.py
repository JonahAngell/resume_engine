"""Requirement parsing on the posting shapes real career sites use.

Each posting here is written for the test, modelled on formats seen on live postings
(see tools/job_parsing_eval.py, which scores the parser against a downloaded sample).
"""

import pytest

from app.job_match import _min_years, match_qualifications, parse_requirements


def rows(text: str, group: str = "required") -> dict[str, list[str]]:
    return {row["text"]: row["keywords"] for row in parse_requirements(text)[group]}


@pytest.mark.parametrize(
    "heading",
    [
        "Requirements:",
        "Job Qualifications",
        "Who you are",
        "What we're looking for:",
        "Must have:",
        "**Required Skills**",
        "## Key Qualifications",
        "WHAT YOU'LL BRING",
        "Required Education, Experience/Skills/Training:",
        "Here’s what you will need to be successful in the job:",
        "Expected areas of competence (i.e. personal skills & attributes):",
    ],
)
def test_requirement_headings_worded_many_ways(heading):
    found = rows(f"{heading}\n- Experience with Tableau\n- Proficiency in SQL\n")
    assert found == {"Experience with Tableau": ["Tableau"], "Proficiency in SQL": ["SQL"]}


@pytest.mark.parametrize("heading", ["Bonus points:", "Nice-to-haves", "It would be a plus if you also have these skills:", "Desired Skills"])
def test_preferred_headings(heading):
    parsed = parse_requirements(f"Requirements:\n- SQL\n{heading}\n- Kubernetes\n")
    assert [row["keywords"] for row in parsed["preferred"]] == [["Kubernetes"]]
    assert [row["keywords"] for row in parsed["required"]] == [["SQL"]]


def test_a_requirement_line_is_not_mistaken_for_a_heading():
    text = "Required Qualifications\nCommunication skills\nExperience with PowerBI\nSkills and Experience\n- Excel\n"
    assert list(rows(text)) == ["Communication skills", "Experience with PowerBI"]
    assert list(rows(text, "preferred")) == ["Excel"]


def test_pay_and_accommodation_sections_end_the_requirements():
    found = rows("Requirements:\n- SQL\nPay Transparency\n- Experience with Workday benefits enrollment\n")
    assert list(found) == ["SQL"]


def test_page_title_above_the_posting_is_not_a_requirements_section():
    text = "Job Requirements\nAcme makes software for theme parks and loves Python.\n\nAbout the role\n- Build reports\n"
    assert rows(text) == {}


def test_skills_outside_the_dictionary_become_phrase_keywords():
    found = rows(
        "Required Qualifications:\n"
        "- Hands-on experience with Unreal Engine, including editor tooling\n"
        "- In-depth knowledge of building and fire codes\n"
        "- Previous experience with DScribe or similar Content Management System\n"
        "- Stochastic optimization\n"
    )
    assert found["Hands-on experience with Unreal Engine, including editor tooling"][0] == "Unreal Engine"
    assert found["In-depth knowledge of building and fire codes"] == ["building and fire codes"]
    assert "DScribe" in found["Previous experience with DScribe or similar Content Management System"]
    assert found["Stochastic optimization"] == ["stochastic optimization"]


def test_phrase_keyword_matches_the_same_words_in_another_form():
    posting = "Requirements:\n- Experience building visual search systems for video\n"
    hit = match_qualifications(posting, {"work_experience": [{"title": "Engineer", "bullets": ["Built a visual search system for 2M clips"]}]})
    miss = match_qualifications(posting, {"work_experience": [{"title": "Engineer", "bullets": ["Built a search page"]}]})
    keyword = hit["required"][0]["keywords"][0]
    assert keyword["found"] and keyword["relation"] == "phrase"
    assert not miss["required"][0]["matched"]


def test_requirements_written_as_a_paragraph():
    text = (
        "We are looking for an analyst who has hands-on experience with SQL, Python and Tableau, and who can partner "
        "with finance stakeholders to build forecasting models for the business every quarter. Ideally you have "
        "worked with Snowflake and dbt in a modern data stack, and you are comfortable presenting insights to executives."
    )
    parsed = parse_requirements(text)
    assert {"SQL", "Python", "Tableau"} <= set(parsed["required"][0]["keywords"])
    assert "Snowflake" in parsed["preferred"][0]["keywords"]


def test_company_blurb_paragraph_under_a_heading_adds_nothing():
    blurb = " ".join(["Acme Theatrical Group was formed in 1994 and produces The Lion Show on Broadway and around the world."] * 3)
    assert rows(f"Requirements:\n{blurb}\n- SQL\n") == {"SQL": ["SQL"]}


@pytest.mark.parametrize(
    "text,years",
    [
        ("Minimum of 3 year of related work experience", 3),
        ("3 years of experience in sales", 3),
        ("At least five years experience", 5),
        ("Three or more years of professional experience", 3),
        ("5+ years", 5),
    ],
)
def test_years_written_many_ways(text, years):
    assert _min_years(text) == years


def test_short_degree_abbreviations():
    parsed = parse_requirements("Requirements:\n- BA in Communications, Journalism, or a related field\n")
    assert [row["kind"] for row in parsed["eligibility"]] == ["degree"]
