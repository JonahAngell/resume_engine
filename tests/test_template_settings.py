"""Custom template settings: defaults per built-in, validation, and the CSS they produce."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ats_score import _parsing
from app.render import font_css_for, render_resume, tools_layout_for
from app.template_settings import (
    BASE_STYLES,
    FONTS,
    defaults_for,
    options,
    resolve_settings,
    settings_css,
    strict_settings,
)

ROOT = Path(__file__).resolve().parents[1]
SEED = json.loads((ROOT / "seed/nia-calder-resume.json").read_text(encoding="utf-8"))
RESUME = SEED.get("resume", SEED)


@pytest.mark.parametrize("base", BASE_STYLES)
def test_unchanged_template_renders_exactly_like_its_base(base):
    settings = resolve_settings(base, {})
    assert settings_css(base, settings) == ""
    plain = render_resume(RESUME, False, template_style=base)
    custom = render_resume(RESUME, False, template_style=base, appearance={"settings": settings})
    assert custom.replace(" custom-template", "") == plain


def test_every_embedded_font_has_files():
    from app.render import FONT_CSS_BY_FAMILY

    for font_id, (_label, _stack, family) in FONTS.items():
        if family:
            assert FONT_CSS_BY_FAMILY.get(family, "").count("@font-face") == 4, font_id


def test_only_changed_settings_produce_css():
    settings = resolve_settings("classic", {"accent_color": "#AA0000", "margins": {"top": 1}})
    css = settings_css("classic", settings)
    assert "color: #aa0000" in css and "--pad-top: 1in" in css and "--content-height: 9.45in" in css
    assert "font-family" not in css and "line-height" not in css and "list-style" not in css


def test_each_setting_maps_to_css():
    settings = resolve_settings(
        "dais",
        {
            "font": "inter",
            "sizes": {"name": 24, "heading": 12, "title": 12, "body": 10, "contact": 9},
            "text_color": "#111111",
            "rule_color": "#00ff00",
            "heading_case": "normal",
            "heading_bold": False,
            "heading_rule": "underline",
            "bullet": "square",
            "date_position": "inline",
            "line_height": 1.4,
            "section_gap": 12,
            "bullet_gap": 2,
        },
    )
    css = settings_css("dais", settings)
    for fragment in (
        "font-family: Inter",
        ".header h1 { font-size: 24pt",
        ".section-title { font-size: 12pt",
        ".row .role { font-size: 12pt",
        ".contact { font-size: 9pt",
        "font-size: 10pt",
        "color: #111111",
        "text-transform: none",
        "font-weight: 400",
        "border-bottom: 1px solid #00ff00",
        'content: "▪"',
        "justify-content: flex-start",
        "line-height: 1.4",
        "margin-bottom: 12pt",
        "margin-bottom: 2pt",
    ):
        assert fragment in css, fragment
    assert all(line.startswith("body.custom-template") for line in css.splitlines())


def test_sre_bullet_keeps_its_own_indent():
    css = settings_css("sre", resolve_settings("sre", {"bullet": "dash"}))
    assert 'li::before { content: "–"; }' in css and "list-style" not in css


def test_stored_values_fall_back_field_by_field():
    settings = resolve_settings("harvard", {"font": "comic-sans", "accent_color": "#123456", "margins": {"top": 9}, "unknown": 1})
    assert settings["font"] == "carlito" and settings["accent_color"] == "#123456"
    assert settings["margins"] == defaults_for("harvard")["margins"]


def test_strict_settings_reject_bad_input():
    assert strict_settings("classic", {"line_height": 1.5})["line_height"] == 1.5
    for bad in ({"line_height": 2}, {"accent_color": "blue"}, {"font": "papyrus"}, {"extra": 1}, {"sizes": {"body": 30}}):
        with pytest.raises(ValidationError):
            strict_settings("classic", bad)


def test_font_and_tools_layout_follow_the_template():
    lato = resolve_settings("classic", {"font": "lato"})
    assert "font-family:'Lato'" in font_css_for("classic", lato)
    assert font_css_for("classic", None) == ""
    assert tools_layout_for("sre") == "table" and tools_layout_for("classic") == "inline"
    assert tools_layout_for("classic", resolve_settings("classic", {"tools_layout": "table"})) == "table"
    assert tools_layout_for("sre", None, "inline") == "inline"
    table = render_resume(RESUME, False, template_style="harvard", appearance={"tools_layout": "table"})
    assert '<table class="skill-table item"' in table


def test_ats_counts_a_table_on_any_template():
    resume = {"tool_groups": [{"name": "x"}], "education": [{}], "work_experience": [{"date": "2024"}], "header": {"email": "a", "phone": "b"}}
    plain = _parsing(resume, {"template_style": "classic"})
    table = _parsing(resume, {"template_style": "classic", "tools_layout": "table"})
    effective = _parsing(resume, {"template_style": "sre", "tools_layout_effective": "inline"})
    assert table["earned"] < plain["earned"] == effective["earned"]


def test_options_describe_every_base_and_limit():
    data = options()
    assert [base["id"] for base in data["bases"]] == list(BASE_STYLES)
    assert data["limits"]["line_height"] == {"min": 1.0, "max": 1.6}
    assert data["limits"]["sizes.name"] == {"min": 10, "max": 32}


def test_migration_links_templates_by_owner():
    sql = (ROOT / "backend/migrations/027_resume_templates.sql").read_text(encoding="utf-8")
    assert "REFERENCES resume_templates (id, user_id) ON DELETE SET NULL (template_id)" in sql
    assert "'template_settings',t.settings" in sql
