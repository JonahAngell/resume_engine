from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_migration_additive_and_normalized():
    s = (ROOT / "backend/migrations/011_phase2k_library_management.sql").read_text(
        encoding="utf-8"
    )
    assert (
        "DROP TABLE" not in s.upper()
        and "library_tags" in s
        and "library_bullet_tags" in s
        and "ownership mismatch" in s
    )


def test_routes_and_stable_order():
    m = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    x = (ROOT / "backend/app/phase2k_repository.py").read_text(encoding="utf-8")
    for value in [
        "/api/library-management/items",
        "/api/library-management/counts",
        "/api/library-management/tags",
        "/usage",
        "/bulk",
    ]:
        assert value in m
    assert (
        "ORDER BY lower(COALESCE(d.body" in x
        and "b.id LIMIT" in x
        and "user_id=%s" in x
    )


def test_tags_not_added_to_render_schema():
    s = (ROOT / "backend/app/schemas.py").read_text(encoding="utf-8")
    assert "library_tags" not in s and "tags:" not in s

def test_parent_assignment_is_owner_scoped_and_compatible():
    m = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    x = (ROOT / "backend/app/phase2k_repository.py").read_text(encoding="utf-8")
    schema = (ROOT / "backend/app/library_schemas.py").read_text(encoding="utf-8")
    assert "/api/library-management/items/{bullet_id}/parent" in m
    assert "async def update_parent" in x and "user_id=%s" in x
    assert "archived_at IS NULL" in x and "parent_type!='content_item'" in x
    assert "class LibraryParentWrite" in schema
