from pathlib import Path
from api_source import api_source

ROOT = Path(__file__).resolve().parents[1]


def test_phase2_migration_is_additive_and_has_history():
    s = (ROOT / "backend/migrations/004_phase2_historical_library.sql").read_text(
        encoding="utf-8"
    )
    assert "DROP TABLE" not in s.upper() and "TRUNCATE" not in s.upper()
    assert (
        "CREATE TABLE composition_revisions" in s
        and "CREATE TABLE custom_sections" in s
    )


def test_phase2_routes_and_security_contracts():
    s = api_source()
    assert (
        "/api/library/search" in s
        and "/revisions" in s
        and "Depends(resolve_current_user)" in s
    )
    r = (ROOT / "backend/app/library_repository.py").read_text(encoding="utf-8")
    assert "user_id=%s" in r and "ILIKE %s" in r


def test_renderer_remains_canonical_and_dynamic():
    s = (ROOT / "backend/app/templates/resume.html").read_text(encoding="utf-8")
    assert (
        "resume.section_order" in s
        and "resume.interest_layout" in s
        and "key.startswith('custom:')" in s
    )
