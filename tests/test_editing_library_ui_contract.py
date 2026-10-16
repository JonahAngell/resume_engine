from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_editing_page_uses_library_actions():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    dialogs = (ROOT / "frontend/src/editor/EditorLibraryDialogs.tsx").read_text(
        encoding="utf-8"
    )
    icons = (ROOT / "frontend/src/AppIcon.tsx").read_text(encoding="utf-8")
    for text in [
        "Edit profile",
        "Choose a profile",
        "Choose a summary",
        "Show ${skill.name} on this resume",
        "Manage skills",
        "+ Add Interest",
        "+ Add Bullet",
        "hidden-tools",
    ]:
        assert text in app or text in dialogs
    assert "pencil" in icons and "replace" in icons
    panel = app.split("function SectionsPanel", 1)[1]
    assert "Summary variant" not in panel
    assert "Add new profile" not in panel
    assert "Select a profile" not in panel
    assert '["manual", "Manual"]' in panel and "aria-pressed" in panel


def test_education_bullets_and_skill_visibility_contract():
    library = (ROOT / "backend/app/library_repository.py").read_text(encoding="utf-8")
    placements = (ROOT / "backend/app/phase2j_repository.py").read_text(encoding="utf-8")
    migration = (
        ROOT / "backend/migrations/019_composition_hidden_tools.sql"
    ).read_text(encoding="utf-8")
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    assert '"id": str(row["id"])' in library
    assert "composition_hidden_tools" in library
    assert "set_tool_visibility" in library
    assert "destination_parent_id" in placements
    assert "NULL" not in placements.split("async def create_and_place")[1].split("async def ")[0]
    assert "composition_hidden_tools" in migration
    assert "/api/compositions/{cid}/hidden-tools" in main
    assert "/api/compositions/{cid}/tools/{tool_id}" in main


def test_resume_bullet_reorder_contract():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    library = (ROOT / "backend/app/library_repository.py").read_text(encoding="utf-8")
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    migration = (
        ROOT / "backend/migrations/020_composition_tool_order.sql"
    ).read_text(encoding="utf-8")
    assert "bullet-placements/order" in app
    assert "DragHandle" in app
    assert "composition_tool_order" in library
    assert "set_tool_order" in library
    assert "NULLS LAST" in library
    assert "/api/compositions/{cid}/tool-order" in main
    assert "/api/compositions/{cid}/tool-groups/{group_id}/tools/order" in main
    assert "composition_tool_order" in migration
