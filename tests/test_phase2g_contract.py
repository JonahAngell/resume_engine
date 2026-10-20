from pathlib import Path
from api_source import api_source

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


def test_generated_default_names_adopt_display_title_within_limit():
    sql = (
        ROOT / "backend/migrations/018_resume_name_from_display_title.sql"
    ).read_text(encoding="utf-8")
    assert "DROP " not in sql.upper() and "display_title =" not in sql
    assert "left(rec.title, 120)" in sql
    assert "''s Resume" in sql
    assert "char_length(' (' || suffix::text || ')')" in sql
    assert "INSERT INTO composition_revisions" in sql


def test_phase2g_api_and_ui_contracts():
    main = api_source()
    ui = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "defaultSetId ? { default_set_id: defaultSetId } : { entire_library: true }" in ui
    assert 'prompt("Composition name")' not in ui
    dialogs = (ROOT / "frontend/src/HomeDialogs.tsx").read_text(encoding="utf-8")
    surfaces = ui + dialogs
    for text in (
        "Resume Details",
        "Resume name",
        "Target company",
        "Target role",
    ):
        assert text in surfaces
    assert "Internal name" not in ui and "Display title" not in ui
    assert "Resume Name" in dialogs
    assert "Internal Name" not in dialogs and "Display Title" not in dialogs
    assert "Job description" in dialogs
    for field in ("display_title", "target_company", "target_role", "job_description_id"):
        assert field in main
        assert field in surfaces
