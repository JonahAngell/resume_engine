from pathlib import Path

from app.phase2l import preprocess_resume
from app.render import normalize_template_style, render_resume, skill_table
from api_source import api_source

ROOT = Path(__file__).resolve().parents[1]

SAMPLE = {
    "header": {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone": "555",
        "linkedin_label": "linkedin.com/in/ada",
    },
    "summary": "Builds reliable systems.",
    "work_experience": [
        {
            "id": "job",
            "organization": "Analytical Engines",
            "title": "Engineer",
            "location": "Remote",
            "date": "2024",
            "bullets": ["Shipped a planner"],
        }
    ],
    "projects": [
        {
            "id": "proj",
            "name": "Atlas",
            "subtitle": "Python",
            "date": "2026",
            "bullets": ["Forecast attendance"],
        }
    ],
    "education": [
        {
            "institution": "USU",
            "location": "Logan, UT",
            "degree": "B.S.",
            "graduation_date": "2024",
        }
    ],
    "tool_groups": [{"name": "Languages", "items": ["Python", "SQL"], "bullets": []}],
    "personal_interests": ["Hiking"],
    "section_order": [
        "summary",
        "work_experience",
        "projects",
        "education",
        "tools",
        "personal_interests",
    ],
}


def test_migration_adds_template_style():
    sql = (ROOT / "backend/migrations/016_template_style.sql").read_text(encoding="utf-8")
    assert "DROP TABLE" not in sql.upper()
    assert "template_style" in sql
    for style in ("classic", "sheets", "harvard", "dais", "sre"):
        assert style in sql


def test_older_revision_without_template_style_renders_classic():
    assert normalize_template_style(None, "classic") == "classic"
    assert normalize_template_style(None, "sheets") == "sheets"
    assert normalize_template_style("harvard", "classic") == "harvard"
    assert normalize_template_style("not-a-style", "classic") == "classic"


def test_each_style_sets_the_page_class_and_skips_coaching_copy():
    coaching = "You’ve got 10 seconds"
    for style, marker in (
        ("classic", "template-classic"),
        ("sheets", "template-sheets"),
        ("harvard", "Experience"),
        ("dais", "template-dais"),
        ("sre", "skill-table"),
    ):
        html = render_resume(SAMPLE, False, "test", {}, "long", style)
        assert f"template-{style}" in html
        assert marker in html
        assert coaching not in html
        assert "data-section-id" in html
        assert "data-bullet-id" in html
    sheets = render_resume(SAMPLE, False, "test", {}, "long", "sheets")
    assert "Python; SQL" in sheets
    harvard = render_resume(SAMPLE, False, "test", {}, "long", "harvard")
    assert " • " in harvard and "Skills &amp; Interests" in harvard
    sre = render_resume(SAMPLE, False, "test", {}, "long", "sre")
    assert "Atlas | Python" in sre
    assert "Summary</h2>" in sre and "Professional Summary" not in sre
    assert " ∙ " in sre
    assert "1.5pt solid #000" in sre and "--pad-top: 0.5in" in sre
    assert "Carlito, Calibri" in sre
    exported = render_resume(SAMPLE, False, "test", {}, "long", "dais")
    preview = render_resume(SAMPLE, True, "test", {}, "long", "dais")
    assert "template-dais" in exported and "template-dais" in preview


def test_preferences_and_editor_wire_style_and_coaching():
    main = api_source()
    repo = (ROOT / "backend/app/phase2l_repository.py").read_text(encoding="utf-8")
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    coaching = (ROOT / "frontend/src/resumeCoaching.ts").read_text(encoding="utf-8")
    template = (ROOT / "backend/app/templates/resume.html").read_text(encoding="utf-8")
    assert "template_style" in repo
    assert main.count('materialized.get("template_style","classic")') >= 2
    assert "Template" in app
    details = app.split("function ResumeDetails", 1)[1].split("function HomeScreen", 1)[0]
    for label in ("Default", "Ruled Serif", "Harvard Style", "Times Serif", "Skill Table"):
        assert f'label: "{label}"' in details
    assert 'label: "Current"' not in details
    assert "SheetsResume" not in details
    assert "firstJobCoaching" in app and "dateFormatCoaching" in app
    assert "You’ve got 10 seconds" in coaching
    assert "You’ve got 10 seconds" not in template
    assert "resume.interest_layout" in template and "{% if measure %}" in template
    sections = app.split("function SectionsPanel", 1)[1]
    assert "Skill rows" not in details
    assert "Skill rows" in sections and "Auto-fit" in sections
    assert "Decrease skill rows" in sections and "Increase skill rows" in sections


def test_sre_skills_wrap_after_the_row_max():
    groups = [
        {"name": "Technical Languages", "items": ["SQL", "Python", "R", "JavaScript"]},
        {"name": "Platforms", "items": [f"P{i}" for i in range(8)]},
    ]
    packed = skill_table(groups, 4)
    assert [len(block["columns"]) for block in packed["blocks"]] == [1, 2]
    assert packed["blocks"][1]["columns"][1] == ["P4", "P5", "P6", "P7"]
    wider = skill_table(groups, 8)
    assert [len(block["columns"]) for block in wider["blocks"]] == [1, 1]
    html = render_resume(
        {
            "header": SAMPLE["header"],
            "tool_groups": groups,
            "section_order": ["tools"],
        },
        False,
        "test",
        {},
        "long",
        "sre",
        4,
    )
    assert 'colspan="2"' in html and "- P4" in html and "Technical Languages:" in html
    assert "You’ve got 10 seconds" not in html


def test_adjacent_company_name_is_shown_once():
    rows = [
        {"id": "a", "organization": "Disney", "title": "Analyst", "location": "Orlando", "date": "2025", "manual_order": 0, "bullets": ["Led"]},
        {"id": "b", "organization": "Disney", "title": "Intern", "location": "Orlando", "date": "2024", "manual_order": 1, "bullets": ["Built"]},
        {"id": "c", "organization": "Huntsman", "title": "Ambassador", "location": "Logan", "date": "2023", "manual_order": 2, "bullets": []},
        {"id": "d", "organization": "Disney", "title": "Host", "location": "Orlando", "date": "2022", "manual_order": 3, "bullets": []},
    ]
    prepared = preprocess_resume({"work_experience": rows}, {"work_experience": "manual"})
    flags = [row["suppress_organization"] for row in prepared["work_experience"]]
    assert flags == [False, True, False, False]
    html = render_resume(
        {"header": SAMPLE["header"], "work_experience": rows, "section_order": ["work_experience"]},
        False,
        "test",
        {"work_experience": "manual"},
        "long",
        "sheets",
    )
    second = html.split('data-item-id="b"', 1)[1].split("</article>", 1)[0]
    assert "Intern" in second and "2024" in second
    assert "Disney" not in second and "Orlando" not in second
    assert html.count("Disney") == 2


def test_each_template_embeds_only_the_font_family_its_css_uses():
    import re

    from app.render import STYLE_FONTS, TEMPLATE_STYLES, font_css_for

    template = (ROOT / "backend/app/templates/resume.html").read_text(encoding="utf-8")
    assert set(STYLE_FONTS) == TEMPLATE_STYLES
    for style in TEMPLATE_STYLES - {"classic"}:
        block = re.search(r"body\.template-%s \{(.*?)\}" % style, template, re.S).group(1)
        first = re.search(r"font-family:\s*\"?([^\",;]+)", block).group(1)
        assert first == STYLE_FONTS[style]
        assert f"font-family:'{first}'" in font_css_for(style)
    assert font_css_for("classic") == ""
