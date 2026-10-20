
from pathlib import Path
from api_source import api_source

ROOT = Path(__file__).resolve().parents[1]


def test_standalone_library_route_and_workspace():
    ui = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    page = (ROOT / "frontend/src/StandaloneLibrary.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/resume-print.css").read_text(encoding="utf-8")
    for text in (
        'screen === "library"',
        'location.hash = "library"',
        "StandaloneLibrary",
    ):
        assert text in ui
    for text in (
        "Reusable Library",
        "Library Sections",
        "List View",
        "Card View",
        "Variants",
        "Usage",
        "Add New ▾",
    ):
        assert text in page
    assert "@media (max-width: 780px)" in css and ".library-details" in css
    assert "ResizeObserver" in page and "pageSize" in page
    assert 'aria-label="Section filter"' not in page
    assert "Use in a Resume" not in page
    assert "SectionSelect" in page and "library-section-pill" in page


def test_library_detail_is_owner_scoped():
    main = api_source()
    repo = (ROOT / "backend/app/phase2k_repository.py").read_text(encoding="utf-8")
    assert (
        "/api/library-management/items/{bullet_id}" in main and "phase2k_detail" in main
    )
    assert (
        "async def detail" in repo and "b.user_id=%s" in repo and "t.user_id=%s" in repo
    )

