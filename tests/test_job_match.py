from pathlib import Path

from app.job_match import (
    analyze_requirements,
    extract_keywords,
    keywords_from_requirement,
    match_qualifications,
    match_resume,
    parse_requirements,
)

ROOT = Path(__file__).resolve().parents[1]

DESCRIPTION = "Required skills: Kubernetes, Terraform, production incident response."
RESUME = {
    "summary": "Builds platforms.",
    "tool_groups": [
        {"name": "Cloud", "items": ["Kubernetes", "Terraform"], "bullets": []}
    ],
    "work_experience": [
        {
            "organization": "Analytical Engines",
            "title": "Engineer",
            "bullets": ["Shipped a planner"],
        }
    ],
}


def keywords(text: str) -> set[str]:
    return {item["keyword"].lower() for item in extract_keywords(text)}


def test_skill_in_the_resume_is_included():
    result = match_resume(DESCRIPTION, RESUME)
    included = {item["keyword"].lower(): item["section"] for item in result["included"]}
    assert included["kubernetes"] == "Skills"
    assert included["terraform"] == "Skills"


def test_missing_phrase_suggests_a_section():
    result = match_resume(DESCRIPTION, RESUME)
    missing = {item["keyword"].lower(): item for item in result["missing"]}
    hit = missing["production incident response"]
    assert hit["section"] == "Skills"
    assert "if you use it" in hit["suggestion"]
    assert result["included_count"] == 2
    assert result["missing_count"] == 1
    assert result["keyword_count"] == 3


def test_keyword_reports_the_section_that_contains_it():
    result = match_resume(
        "Required skills: Kubernetes, Terraform, Grafana.",
        {
            "tool_groups": [{"name": "Cloud", "items": ["Terraform"], "bullets": []}],
            "work_experience": [
                {
                    "organization": "Engines",
                    "title": "SRE",
                    "bullets": ["Ran Kubernetes upgrades"],
                }
            ],
        },
    )
    included = {item["keyword"].lower(): item["section"] for item in result["included"]}
    assert included["kubernetes"] == "Work Experience"
    assert included["terraform"] == "Skills"
    assert "grafana" in {item["keyword"].lower() for item in result["missing"]}


def test_generic_posting_words_are_ignored():
    found = keywords(
        "Strong experience on a team. Responsibilities include shipping software."
    )
    for word in ("experience", "team", "responsibilities", "strong"):
        assert word not in found


def test_longer_phrase_replaces_the_words_it_covers():
    found = keywords(
        "Site Reliability and Site Reliability engineering work. Site Reliability matters."
    )
    assert "site reliability" in found
    assert "site" not in found
    assert "reliability" not in found


def test_composition_job_link_migration_is_additive():
    sql = (ROOT / "backend/migrations/022_composition_job_link.sql").read_text(encoding="utf-8")
    assert "DROP " not in sql.upper() and "TRUNCATE" not in sql.upper()
    assert "ADD COLUMN job_description_id" in sql
    assert "ON DELETE SET NULL" in sql
    assert "HAVING count(*) = 1" in sql
    repository = (ROOT / "backend/app/editing_repository.py").read_text(encoding="utf-8")
    jobs = (ROOT / "backend/app/job_repository.py").read_text(encoding="utf-8")
    assert "link_job" in repository
    assert "WHERE job_description_id=%s AND user_id=%s" in jobs
    compare = jobs.split("async def compare_job_description", 1)[1].split("async def ", 1)[0]
    assert "SET composition_id=%s" in compare
    assert "resume_compositions" not in compare


def test_job_description_migration_is_additive():
    sql = (ROOT / "backend/migrations/020_job_descriptions.sql").read_text(encoding="utf-8")
    assert "DROP TABLE" not in sql.upper()
    assert "CREATE TABLE job_descriptions" in sql
    assert "ON DELETE SET NULL" in sql
    assert "job_descriptions_user_updated" in sql


DISNEY = """
About the Role
The team builds marketing models.

You Will Have / Required Qualifications
- Demonstrated experience with Python
- Familiarity with SQL, Tableau, and Spark
- Strong experience on a team

Preferred Qualifications
- Experience with Python, SQL, and PySpark
- Experience with cloud platforms such as AWS, Databricks, or Snowflake
- Experience with tools (e.g., JIRA, Confluence)
- Hands-on experience with practices such as Agile, Lean, Kanban, Waterfall
- Proficiency in SQL/Oracle query language

Responsibilities
- Build dashboards for the marketing team
"""


def _keywords(rows):
    return [keyword.lower() for row in rows for keyword in row["keywords"]]


def test_required_and_preferred_sections_are_separate_rows():
    parsed = parse_requirements(DISNEY)
    required = [row["text"] for row in parsed["required"]]
    preferred = [row["text"] for row in parsed["preferred"]]
    assert any("Demonstrated experience with Python" in text for text in required)
    assert any("Tableau" in text for text in required)
    assert any("PySpark" in text for text in preferred)
    assert any("SQL/Oracle" in text for text in preferred)
    assert all("marketing models" not in text.lower() for text in required + preferred)
    assert all("Build dashboards" not in text for text in required + preferred)
    assert "python" in _keywords(parsed["required"])
    assert "pyspark" in _keywords(parsed["preferred"])
    assert "sql" in _keywords(parsed["preferred"])
    assert "oracle" in _keywords(parsed["preferred"])
    for word in ("team", "strong", "experience", "skills"):
        assert word not in _keywords(parsed["required"] + parsed["preferred"])


def test_requirement_sentence_keeps_the_tool():
    assert keywords_from_requirement("Demonstrated experience with Python") == ["Python"]
    assert keywords_from_requirement(
        "Experience with tools (e.g., JIRA, Confluence)"
    ) == ["JIRA", "Confluence"]
    assert keywords_from_requirement("Proficiency in SQL/Oracle query language") == ["SQL", "Oracle"]


def test_python_requirement_matches_resume_text_or_a_bullet_tag():
    wording = "Required Qualifications\nDemonstrated experience with Python\n"
    from_resume = match_qualifications(wording, {"summary": "Uses Python for analysis"})
    assert from_resume["required"][0]["matched"] is True
    assert from_resume["required_matched"] == 1
    from_tag = match_qualifications(
        wording,
        {"summary": "Builds models for stakeholders"},
        bullets=[
            {
                "id": "b1",
                "wording": "Built marketing models",
                "tags": ["Python"],
                "section": "Work Experience",
            }
        ],
    )
    assert from_tag["required"][0]["matched"] is True
    assert from_tag["required"][0]["keywords"][0]["keyword"] == "Python"


def test_missing_keyword_suggests_the_closest_bullet_tag():
    result = match_qualifications(
        "Required Qualifications\nDemonstrated experience with Python and stakeholder analysis\n",
        {"summary": "Builds models"},
        bullets=[
            {
                "id": "far",
                "wording": "Maintained warehouse tables",
                "tags": [],
                "section": "Work Experience",
            },
            {
                "id": "near",
                "wording": "Owned stakeholder analysis for the marketing team",
                "tags": [],
                "section": "Work Experience",
            },
        ],
    )
    row = result["required"][0]
    assert row["matched"] is False
    suggestion = row["suggestions"][0]
    assert suggestion["keyword"] == "Python"
    assert suggestion["bullet_id"] == "near"
    assert 'tag "Python"' in suggestion["suggestion"]
    assert len(row["suggestions"]) == 2
    assert row["suggestions"][1]["section"] == "Skills"
    assert row["suggestions"][1]["line_id"] == "tools"
    assert result["required_matched"] == 0
    assert result["required_count"] == 1


def test_missing_keyword_without_a_bullet_points_at_skills():
    result = match_qualifications(
        "Basic Qualifications\nDemonstrated experience with Python\n",
        {"summary": "Builds models"},
    )
    suggestion = result["required"][0]["suggestions"][0]
    assert suggestion["bullet_id"] is None
    assert suggestion["section"] == "Skills"
    assert suggestion["line_id"] == "tools"
    assert "Skills" in suggestion["suggestion"]
    assert len(result["required"][0]["suggestions"]) == 1


def test_related_skill_outranks_an_unrelated_bullet():
    result = match_qualifications(
        "Required Qualifications\nDemonstrated experience with Python\n",
        {"summary": "Builds models"},
        bullets=[
            {
                "id": "unrelated",
                "wording": "Maintained warehouse tables",
                "tags": [],
                "section": "Work Experience",
            },
            {
                "id": "pandas",
                "wording": "Built dashboards in pandas",
                "tags": [],
                "section": "Work Experience",
            },
        ],
    )
    suggestions = result["required"][0]["suggestions"]
    assert suggestions[0]["bullet_id"] == "pandas"
    assert "pandas" in suggestions[0]["suggestion"]
    assert "related to Python" in suggestions[0]["suggestion"]
    assert len(suggestions) == 2


def test_requirement_words_outrank_a_related_skill():
    result = match_qualifications(
        "Required Qualifications\nDemonstrated experience with Python and stakeholder analysis\n",
        {"summary": "Builds models"},
        bullets=[
            {
                "id": "pandas",
                "wording": "Built dashboards in pandas",
                "tags": [],
                "section": "Work Experience",
            },
            {
                "id": "near",
                "parent_id": "job-1",
                "line_index": 2,
                "wording": "Owned stakeholder analysis for the marketing team",
                "tags": [],
                "section": "Work Experience",
            },
        ],
    )
    suggestions = result["required"][0]["suggestions"]
    assert suggestions[0]["bullet_id"] == "near"
    assert suggestions[0]["line_id"] == "job-1-bullet-2"
    assert suggestions[1]["bullet_id"] == "pandas"


def test_related_skill_group_is_a_placement_option():
    result = match_qualifications(
        "Required Qualifications\nDemonstrated experience with Python\n",
        {"tool_groups": [{"name": "Analysis", "items": ["pandas", "SQL"]}]},
        bullets=[
            {
                "id": "far",
                "wording": "Maintained warehouse tables",
                "tags": [],
                "section": "Work Experience",
            }
        ],
    )
    suggestion = result["required"][0]["suggestions"][0]
    assert suggestion["line_id"] == "tool-group-0"
    assert suggestion["section"] == "Skills"
    assert "pandas" in suggestion["suggestion"]


def test_combination_needs_every_term():
    result = match_qualifications(
        "Required Qualifications\nDemonstrated experience with data engineering\n",
        {"summary": ""},
        bullets=[
            {
                "id": "partial",
                "wording": "Wrote Python scripts for reporting",
                "tags": [],
                "section": "Work Experience",
            },
            {
                "id": "both",
                "wording": "Moved Python models onto SQL warehouses",
                "tags": [],
                "section": "Projects",
            },
        ],
    )
    assert result["required"][0]["keywords"][0]["keyword"] == "Data Engineering"
    suggestions = result["required"][0]["suggestions"]
    assert suggestions[0]["bullet_id"] == "both"
    assert "Python and SQL" in suggestions[0]["suggestion"]


def test_alias_spelling_outranks_an_unrelated_bullet():
    result = match_qualifications(
        "Required Qualifications\nDemonstrated experience with Python\n",
        {"summary": "Builds models"},
        bullets=[
            {
                "id": "unrelated",
                "wording": "Maintained warehouse tables",
                "tags": [],
                "section": "Work Experience",
            },
            {
                "id": "sklearn",
                "wording": "Trained forecasting models with sklearn",
                "tags": [],
                "section": "Work Experience",
            },
        ],
    )
    suggestions = result["required"][0]["suggestions"]
    assert suggestions[0]["bullet_id"] == "sklearn"
    assert "scikit-learn" in suggestions[0]["suggestion"]


def test_phrase_outranks_an_unrelated_bullet():
    result = match_qualifications(
        "Required Qualifications\nDemonstrated experience with Python\n",
        {"summary": "Builds models"},
        bullets=[
            {
                "id": "unrelated",
                "wording": "Maintained warehouse tables",
                "tags": [],
                "section": "Work Experience",
            },
            {
                "id": "ml",
                "wording": "Shipped a machine learning model for pricing",
                "tags": [],
                "section": "Work Experience",
            },
        ],
    )
    suggestions = result["required"][0]["suggestions"]
    assert suggestions[0]["bullet_id"] == "ml"
    assert "machine learning" in suggestions[0]["suggestion"]


def test_dotnet_name_outranks_an_unrelated_bullet():
    result = match_qualifications(
        "Required Qualifications\nDemonstrated experience with C#\n",
        {"summary": "Builds services"},
        bullets=[
            {
                "id": "unrelated",
                "wording": "Maintained warehouse tables",
                "tags": [],
                "section": "Work Experience",
            },
            {
                "id": "dotnet",
                "wording": "Built internal services on .NET",
                "tags": [],
                "section": "Work Experience",
            },
        ],
    )
    suggestions = result["required"][0]["suggestions"]
    assert suggestions[0]["bullet_id"] == "dotnet"
    assert "dotnet" in suggestions[0]["suggestion"]


def test_node_js_name_outranks_an_unrelated_bullet():
    result = match_qualifications(
        "Required Qualifications\nDemonstrated experience with JavaScript\n",
        {"summary": "Builds services"},
        bullets=[
            {
                "id": "unrelated",
                "wording": "Maintained warehouse tables",
                "tags": [],
                "section": "Work Experience",
            },
            {
                "id": "node",
                "wording": "Built APIs in node.js",
                "tags": [],
                "section": "Work Experience",
            },
        ],
    )
    suggestions = result["required"][0]["suggestions"]
    assert suggestions[0]["bullet_id"] == "node"
    assert "node.js" in suggestions[0]["suggestion"]


def test_r_language_outranks_an_unrelated_bullet():
    result = match_qualifications(
        "Required Qualifications\nDemonstrated experience with statistics\n",
        {"summary": "Studies experiments"},
        bullets=[
            {
                "id": "unrelated",
                "wording": "Maintained warehouse tables",
                "tags": [],
                "section": "Work Experience",
            },
            {
                "id": "rlang",
                "wording": "Fit the experiment models in R",
                "tags": [],
                "section": "Work Experience",
            },
        ],
    )
    suggestions = result["required"][0]["suggestions"]
    assert suggestions[0]["bullet_id"] == "rlang"
    assert "related to Statistics" in suggestions[0]["suggestion"]


def test_fallback_requirement_sentence_when_there_is_no_heading():
    parsed = parse_requirements(
        "The team is strong. Demonstrated experience with Python. We ship software."
    )
    assert parsed["preferred"] == []
    assert parsed["required"][0]["keywords"] == ["Python"]


def test_review_can_dismiss_a_row_and_add_one():
    result = match_qualifications(
        "Required Qualifications\nDemonstrated experience with Python\n",
        {"summary": ""},
        review={
            "dismissed": ["Demonstrated experience with Python"],
            "added": [{"group": "preferred", "text": "Familiarity with Snowflake"}],
        },
    )
    assert result["required"] == []
    assert result["preferred"][0]["keywords"][0]["keyword"] == "Snowflake"
    assert result["preferred_count"] == 1
    assert result["preferred_matched"] == 0


def test_required_skills_and_education_stay_in_required():
    parsed = parse_requirements(
        """
Required Qualifications
- Demonstrated experience with Python
- Bachelor's degree in Computer Science

Required Education
- Bachelor's degree in Information Systems or a related field

Preferred Qualifications
- Experience with Tableau

Preferred Education
- Master's degree
"""
    )
    required_kinds = {row["kind"] for row in parsed["required"]}
    assert required_kinds == {"tool"}
    assert any(row["kind"] == "tool" and "Python" in row["keywords"] for row in parsed["required"])
    education = [row for row in parsed["eligibility"] if row["kind"] == "degree"]
    required_education = [row for row in education if row["group"] == "required"]
    assert len(required_education) == 2
    preferred_education = [row for row in education if row["group"] == "preferred"]
    assert len(preferred_education) == 1
    assert preferred_education[0]["label"] == "Master's degree"
    assert any(row["kind"] == "tool" and "Tableau" in row["keywords"] for row in parsed["preferred"])


def test_bachelors_resume_satisfies_bachelors_not_masters():
    resume = {
        "education": [
            {
                "institution": "Utah State University",
                "degree": "Bachelor of Science, Management Information Systems",
            }
        ]
    }
    bachelors = match_qualifications(
        "Required Education\nBachelor's degree in Information Systems or a related field\n",
        resume,
    )
    degree = bachelors["eligibility"]["degree"]
    assert degree["status"] == "pass"
    assert "Management Information Systems" in degree["detail"]
    assert bachelors["required"] == []
    assert bachelors["scores"]["required_coverage"] == 0
    masters = match_qualifications(
        "Preferred Education\nMaster's degree\n",
        resume,
    )
    assert masters["eligibility"]["degree"]["status"] == "fail"
    assert masters["eligibility"]["degree"]["detail"] == "This resume does not list a qualifying degree."
    assert masters["preferred"] == []


def test_masters_resume_satisfies_a_bachelors_requirement():
    result = match_qualifications(
        "Minimum Education\nBachelor's degree in Computer Science\n",
        {"education": [{"degree": "Master of Science, Computer Science", "institution": "State"}]},
    )
    assert result["required"] == []
    assert result["eligibility"]["degree"]["status"] == "pass"
    assert "Computer Science" in result["eligibility"]["degree"]["detail"]


def test_named_field_must_appear_when_the_posting_does_not_allow_related():
    result = match_qualifications(
        "Required Education\nBachelor's degree in Computer Science\n",
        {"education": [{"degree": "Bachelor of Science, Management Information Systems"}]},
    )
    assert result["required"] == []
    assert result["eligibility"]["degree"]["status"] == "fail"


def test_salary_and_location_are_facts_not_requirements():
    posting = """
Required Qualifications
- Demonstrated experience with Python

The hiring range for this position in Glendale, CA is $94,400.00 to $128,000.00 per year.
Location: Orlando, Florida
"""
    result = match_qualifications(posting, {"summary": "Uses Python"})
    assert result["salary"] == "$94,400.00 to $128,000.00 per year"
    assert "Glendale, CA" in result["locations"]
    assert "Orlando, Florida" in result["locations"]
    assert all("per year" not in row["text"].lower() for row in result["required"])
    assert all("orlando" not in row["text"].lower() for row in result["required"])
    assert result["required"][0]["keywords"][0]["keyword"] == "Python"


def test_skill_without_a_keyword_uses_a_short_label():
    parsed = parse_requirements(
        "Required Qualifications\nStrong communication across partner teams and executives\n"
    )
    assert parsed["required"][0]["category"] == "soft_skill"
    assert "communication" in parsed["required"][0]["keywords"]


def test_review_can_mark_a_missing_row_as_matched():
    wording = "Required Qualifications\nDemonstrated experience with Python\n"
    result = match_qualifications(
        wording,
        {"summary": ""},
        review={"matched": ["Demonstrated experience with Python"]},
    )
    row = result["required"][0]
    assert row["matched"] is True
    assert row["manual"] is True
    assert row["keywords"][0]["found"] is False
    assert result["required_matched"] == 1


def test_analyze_requirements_skips_the_resume_and_applies_review():
    posting = (
        "Required Qualifications\n"
        "Demonstrated experience with Python and SQL\n"
        "Preferred Qualifications\n"
        "Familiarity with Snowflake\n"
    )
    result = analyze_requirements(
        posting,
        {
            "dismissed": ["Familiarity with Snowflake"],
            "added": [{"group": "required", "text": "Experience with dbt"}],
        },
    )
    keywords = {keyword.lower() for row in result["required"] for keyword in row["keywords"]}
    assert "python" in keywords
    assert "sql" in keywords
    assert "dbt" in keywords
    assert result["preferred"] == []
    for row in result["required"]:
        assert set(row) == {"text", "kind", "label", "keywords", "match_mode", "category", "section", "weight"}
        assert all(isinstance(keyword, str) for keyword in row["keywords"])


def test_keyword_review_migration_is_additive():
    sql = (ROOT / "backend/migrations/021_job_keyword_review.sql").read_text(encoding="utf-8")
    assert "DROP " not in sql.upper()
    assert "keyword_review" in sql
    assert "jsonb" in sql


def test_qualifications_and_skills_heading_is_required():
    parsed = parse_requirements(
        """
What You Will Do
Run reporting and create automation

Required Qualifications & Skills
Experience with report development utilizing tools such as Tableau, Power BI, Smartsheet or SQL
Skilled in project management tools such as Jira, Confluence, or MS Project
Strong communication skills, with the ability to engage partners

Education
High School Diploma or equivalent required
"""
    )
    keywords = _keywords(parsed["required"])
    assert "tableau" in keywords
    assert "power bi" in keywords
    assert "microsoft project" in keywords
    assert any(row["match_mode"] == "any" and "Tableau" in row["keywords"] for row in parsed["required"])
    assert any(row["category"] == "soft_skill" and "communication" in row["keywords"] for row in parsed["required"])
    assert any(row["kind"] == "degree" and row["label"] == "High school" for row in parsed["eligibility"])


def test_basic_qualifications_and_inline_education():
    parsed = parse_requirements(
        """
Basic Qualifications/You Will Have
Experience supporting project management activities, including coordinating priorities.

Preferred Qualifications
Experience with portfolio tooling such as Smartsheet, Airtable, Bluebeam, SAP, and Maximo.

Education
Bachelor's degree in an engineering or related field is required.
Master's degree in engineering, business, or equivalent is preferred.

Additional Information
Disney offers a rewards package to help you live your best life.
"""
    )
    assert "project management" in _keywords(parsed["required"])
    assert any(
        row["kind"] == "degree" and row["label"] == "Bachelor's degree" and row["group"] == "required"
        for row in parsed["eligibility"]
    )
    assert any(
        row["kind"] == "degree" and row["label"] == "Master's degree" and row["group"] == "preferred"
        for row in parsed["eligibility"]
    )
    assert any(row["match_mode"] == "any" and "Maximo" in row["keywords"] for row in parsed["preferred"])
    assert all("rewards package" not in row["text"].lower() for row in parsed["required"] + parsed["preferred"])


def test_preferences_and_misfiled_requirements_skip_the_company_blurb():
    parsed = parse_requirements(
        """
Job Summary
DE manages production and distribution (including Disney+, Hulu) across broadcast and cable.

Responsibilities and Duties of the Role:
3+ years of finance/accounting related work experience
Bachelor's degree in Finance, Accounting, Economics, or Statistics
Proficient in Excel and PowerPoint; and with financial reporting systems (e.g., Oracle EPM, COGNOS TM1)

Preferences
MBA and/or CPA
Oracle EPM / Smart View
Microsoft Power BI
"""
    )
    blob = " ".join(row["text"] for row in parsed["required"] + parsed["preferred"] + parsed["responsibilities"])
    assert "Disney+" not in blob
    assert "Hulu" not in blob
    assert any("Excel" in row["keywords"] for row in parsed["responsibilities"])
    assert any(row["kind"] == "degree" and "Bachelor" in row["label"] for row in parsed["eligibility"])
    assert any(row["kind"] == "credential" and "CPA" in row["keywords"] for row in parsed["eligibility"])
    assert any(row["kind"] == "degree" and "Master" in row["label"] for row in parsed["eligibility"])
    assert any("Power BI" in row["keywords"] for row in parsed["preferred"])


def test_example_list_matches_when_one_tool_is_present():
    result = match_qualifications(
        "Required Qualifications & Skills\n"
        "Experience with tools such as Tableau, Power BI, Smartsheet or SQL\n",
        {"summary": "Built Tableau dashboards for finance"},
    )
    row = result["required"][0]
    assert row["match_mode"] == "any"
    assert row["matched"] is True
    assert any(item["keyword"] == "Tableau" and item["found"] for item in row["keywords"])
    assert result["required_matched"] == 1


def test_powerbi_is_suggested_and_matched_as_power_bi():
    missing = match_qualifications(
        "Required Qualifications\nExperience with tools such as PowerBI\n",
        {"summary": "No dashboards yet"},
    )
    row = missing["required"][0]
    assert row["keywords"][0]["keyword"] == "Power BI"
    assert "Power BI" in row["suggestions"][0]["suggestion"]
    found = match_qualifications(
        "Required Qualifications\nExperience with tools such as PowerBI\n",
        {"summary": "Shipped PowerBI reports"},
    )
    assert found["required"][0]["matched"] is True
    assert found["required"][0]["keywords"][0]["where"] == "Summary"


def test_my_time_matches_a_workbrain_resume():
    result = match_qualifications(
        "Preferred Qualifications\n"
        "Experience with MY TIME (aka Infor, Workbrain), Zendesk, and/or SAP\n",
        {"summary": "Maintained schedules in Workbrain"},
    )
    row = result["preferred"][0]
    assert row["match_mode"] == "any"
    assert row["matched"] is True
    assert any("time" in item["keyword"].lower() and item["found"] for item in row["keywords"])


def test_communication_only_line_is_a_soft_skill():
    parsed = parse_requirements(
        "Required Qualifications & Skills\n"
        "Strong communication skills, with the ability to engage partners\n"
    )
    assert parsed["required"][0]["category"] == "soft_skill"
    assert parsed["eligibility"] == []
    assert parsed["preferred"] == []


def test_negated_and_example_only_tools_are_not_required():
    parsed = parse_requirements(
        """
What You Will Do
Use a tracker, for example Jira, when the team asks.

Required Qualifications
No experience required with Kubernetes.
Willing to learn Terraform.
Demonstrated experience with Python
"""
    )
    kept = _keywords(parsed["required"] + parsed["responsibilities"])
    assert "jira" not in kept
    assert "kubernetes" not in kept
    assert "terraform" not in kept
    assert "python" in _keywords(parsed["required"])


def test_cluster_evidence_is_weaker_than_an_exact_mention():
    result = match_qualifications(
        "Required Qualifications\nDemonstrated experience with Python\n",
        {"summary": "Analyzed data with pandas"},
    )
    keyword = result["required"][0]["keywords"][0]
    assert keyword["found"] is False
    assert keyword["relation"] == "cluster"
    assert keyword["evidence"]["confidence"] == 0.55
    assert keyword["evidence"]["section"] == "Summary"
    assert result["required"][0]["matched"] is False
    assert result["scores"]["required_coverage"] == 0
    assert result["scores"]["evidence_quality"] == 0.55


def test_tax_and_programme_postings_score_sections_separately():
    tax = (ROOT / "docs/job_description_repository/tax_analyst.md").read_text(encoding="utf-8")
    programme = (ROOT / "docs/job_description_repository/program_engineer.md").read_text(encoding="utf-8")
    parsed = parse_requirements(tax)
    assert any(row["weight"] == 1.0 and row["category"] == "tool" for row in parsed["required"])
    assert any(row["weight"] == 0.65 for row in parsed["responsibilities"])
    assert any(row["kind"] == "degree" for row in parsed["eligibility"])
    assert any(row["match_mode"] == "any" for row in parsed["required"])
    result = match_qualifications(
        tax,
        {
            "summary": "Supported tax technology during a finance transformation",
            "education": [{"degree": "Bachelor of Science, Accounting", "institution": "State"}],
            "work_experience": [
                {
                    "title": "Analyst",
                    "start_year": 2020,
                    "end_year": 2024,
                    "bullets": ["Built Power BI reports for tax compliance"],
                }
            ],
        },
    )
    family_ids = {item["id"] for item in result["families"]}
    assert "tax-technology" in family_ids
    assert "finance-transformation" in family_ids
    assert result["eligibility"]["degree"]["status"] == "pass"
    assert result["eligibility"]["years"]["status"] == "pass"
    assert all(row["category"] not in {"degree", "experience_duration", "credential"} for row in result["required"])
    evidence = next(
        item["evidence"]
        for row in result["required"] + result["preferred"] + result["responsibilities"]
        for item in row["keywords"]
        if item["found"] and item["evidence"]
    )
    assert set(evidence) >= {"source_requirement", "matched_text", "relation", "section", "confidence", "explanation"}
    assert evidence["relation"] in {"exact", "alias"}
    programme_match = match_qualifications(programme, {"summary": "Led portfolio reviews in Bluebeam"})
    assert any(item["id"] == "technical-program" for item in programme_match["families"])
    assert "required_coverage" in programme_match["scores"]
    assert all(
        row["category"] not in {"degree", "experience_duration", "credential"}
        for row in programme_match["required"]
    )


def test_suggestions_carry_placement_and_action():
    result = match_qualifications(
        "Required Qualifications\nExperience with financial forecasting for budgeting teams\n",
        {"summary": "x"},
        bullets=[
            {
                "id": "b1",
                "placement_id": "p1",
                "parent_id": "job-1",
                "line_index": 0,
                "wording": "Owned budgeting reviews for regional teams",
                "tags": [],
                "section": "Work Experience",
            }
        ],
    )
    first, fallback = result["required"][0]["suggestions"]
    assert (first["placement_id"], first["line_id"], first["action"]) == (
        "p1",
        "job-1-bullet-0",
        "rewrite",
    )
    assert (fallback["placement_id"], fallback["line_id"], fallback["action"]) == (
        "",
        "tools",
        "add_skill",
    )


def test_missing_tool_on_a_bullet_is_added_to_skills_not_rewritten():
    result = match_qualifications(
        "Required Qualifications\nDemonstrated experience with Python and stakeholder analysis\n",
        {"summary": "Builds models"},
        bullets=[
            {
                "id": "near",
                "placement_id": "p-near",
                "wording": "Owned stakeholder analysis for the marketing team",
                "tags": [],
                "section": "Work Experience",
            }
        ],
    )
    suggestions = result["required"][0]["suggestions"]
    assert suggestions[0]["placement_id"] == "p-near"
    assert {item["action"] for item in suggestions} == {"add_skill"}


def test_skill_group_option_is_add_skill():
    result = match_qualifications(
        "Required Qualifications\nDemonstrated experience with Python\n",
        {"tool_groups": [{"name": "Analysis", "items": ["pandas", "SQL"]}]},
        bullets=[],
    )
    suggestion = result["required"][0]["suggestions"][0]
    assert suggestion["line_id"] == "tool-group-0"
    assert suggestion["action"] == "add_skill"


def test_keywords_say_whether_they_belong_in_skills():
    job = """Product Analyst

Required Qualifications
- Experience with A/B testing
- Proficiency in Tableau
"""
    match = match_qualifications(job, {"summary": "Analyst"}, [], {})
    flags = {item["keyword"]: item["skill"] for row in match["required"] for item in row["keywords"]}
    assert flags == {"A/B testing": False, "Tableau": True}
