import re
from pathlib import Path
from api_source import api_source

ROOT = Path(__file__).resolve().parents[1]


def test_phase2j_migration_is_additive_and_relationship_complete():
    s = (
        ROOT / "backend/migrations/010_phase2j_reusable_bullet_placements.sql"
    ).read_text(encoding="utf-8")
    assert "DROP TABLE" not in s.upper() and "TRUNCATE" not in s.upper()
    for field in (
        "destination_section",
        "destination_parent_type",
        "destination_parent_id",
        "wording_snapshot",
        "snapshot_source_updated_at",
    ):
        assert field in s
    assert "enforce_phase2j_placement_ownership" in s and "bullet_placements" in s


def test_phase2j_routes_and_atomic_repository_exist():
    main = api_source()
    repo = (ROOT / "backend/app/phase2j_repository.py").read_text(encoding="utf-8")
    for route in ("/api/library/bullet-picker", "/bullet-placements", "/update-usage"):
        assert route in main
    for fn in (
        "insert_placement",
        "create_and_place",
        "remove_placement",
        "replace_placement",
        "reorder_placements",
        "update_usage",
    ):
        assert f"async def {fn}" in repo
    assert (
        repo.count("async with conn.transaction()") >= 6 and "wording_snapshot" in repo
    )


def test_phase2j_placement_ui_contract_remains_available():
    ui = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    modal = (ROOT / "frontend/src/ModalShell.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/resume-print.css").read_text(
        encoding="utf-8"
    )

    # Phase 3c retired the original in-App BulletPicker. Phase 3d
    # supplies the replacement shared picker.
    assert "+ Add Bullet" in ui
    assert "bullet-placements" in ui
    assert 'role="dialog"' in modal
    assert 'aria-modal={variant === "dialog" ? "true" : undefined}' in modal

    assert ".bullet-picker-backdrop" in css
    assert re.search(
        r"@media\s*\(\s*max-width\s*:\s*900px\s*\)",
        css,
    )
