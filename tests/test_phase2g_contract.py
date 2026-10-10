from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase2g_migration_is_additive_and_enriches_history():
    sql = (ROOT / "backend/migrations/009_phase2g_resume_metadata.sql").read_text(
        encoding="utf-8"
    )
    assert "DROP " not in sql.upper() and "TRUNCATE" not in sql.upper()
    for column in ("display_title", "target_company", "target_role"):
        assert f"ADD COLUMN {column}" in sql
        assert f"'{column}'" in sql
    assert "composition_revision_metadata_snapshot" in sql
    assert "enrich_composition_revision_snapshot" in sql


def test_server_generates_unique_default_names_and_metadata_is_owner_scoped():
    repository = (ROOT / "backend/app/editing_repository.py").read_text(
        encoding="utf-8"
    )
    assert "pg_advisory_xact_lock" in repository
    assert "'s Resume (" in repository
    assert "suffix = 2" in repository
    assert "WHERE user_id=%s" in repository
    assert "display_title" in repository
    assert "target_company" in repository
    assert "target_role" in repository


def test_phase2g_api_and_ui_contracts():
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    ui = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "body: JSON.stringify({})" in ui
    assert 'prompt("Composition name")' not in ui
    for text in (
        "Resume Details",
        "Internal name",
        "Display title",
        "Target company",
        "Target role",
    ):
        assert text in ui
    for field in ("display_title", "target_company", "target_role"):
        assert field in main
        assert field in ui
