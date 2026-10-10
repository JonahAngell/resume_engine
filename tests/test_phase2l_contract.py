from pathlib import Path
from app.phase2l import (
    continuous,
    display_date,
    chronological_key,
    preprocess_resume,
    validate_dates,
)

ROOT = Path(__file__).resolve().parents[1]


def test_migration_and_preferences_contract():
    s = (ROOT / "backend/migrations/012_phase2l_date_sorting_metadata.sql").read_text(
        encoding="utf-8"
    )
    assert "DROP TABLE" not in s.upper()
    for x in (
        "preferred_page_length",
        "date_format",
        "section_sort_modes",
        "start_year",
        "is_current",
    ):
        assert x in s


def test_date_validation_and_formatting():
    import pytest

    with pytest.raises(ValueError):
        validate_dates(start_month=1)
    with pytest.raises(ValueError):
        validate_dates(start_year=2026, end_year=2025)
    assert (
        display_date(
            {"start_year": 2025, "start_month": 9, "is_current": True}, "short"
        )
        == "Sep 2025 - Present"
    )
    assert (
        display_date({"date_label": "Custom wording", "start_year": 2025}, "long")
        == "Custom wording"
    )


def test_sort_and_grouping_contract():
    current = {
        "id": "b",
        "organization": "  Example   Co ",
        "start_year": 2025,
        "start_month": 2,
        "is_current": True,
        "manual_order": 1,
    }
    prior = {
        "id": "a",
        "organization": "example co",
        "start_year": 2024,
        "start_month": 1,
        "end_year": 2025,
        "end_month": 1,
        "manual_order": 0,
    }
    assert chronological_key(current) < chronological_key(prior) and continuous(
        prior, current
    )
    punct = {**prior, "organization": "Example Co."}
    assert not continuous(punct, current)
    out = preprocess_resume({"work_experience": [prior, current]})
    assert out["work_experience"][1]["suppress_organization"]

    def test_home_search_and_accessible_warning_present():
        ui = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
        for field in (
            "item.name",
            "item.display_title",
            "item.target_company",
            "item.target_role",
        ):
            assert field in ui

        for text in (
            "Leading recruiters recommend",
            "Preferred page length",
            "Date format",
        ):
            assert text in ui

        assert "query.trim().toLowerCase()" in ui
