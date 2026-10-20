from pathlib import Path
from api_source import api_source

ROOT = Path(__file__).resolve().parents[1]


def test_authoritative_render_and_export_contracts():
    m = api_source()
    repo = (ROOT / "backend/app/phase2m_repository.py").read_text(encoding="utf-8")
    t = (ROOT / "backend/app/templates/resume.html").read_text(encoding="utf-8")
    assert (
        "/api/compositions/{cid}/render" in m
        and "/api/compositions/{cid}/export/pdf" in m
    )
    assert (
        "Raw-payload export is disabled" in m
        and "user_id=%s" in repo
        and "archived_at IS NULL" in repo
    )
    assert (
        "document.fonts.ready" in t
        and "resume-page" in t
        and "data-page-index" in t
        and "oversized_item_ids" in t
    )


def test_preview_navigation_and_export_enforcement():
    ui = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    preview = (ROOT / "frontend/src/ResumePreview.tsx").read_text(encoding="utf-8")
    coordinator = (ROOT / "frontend/src/SaveCoordinator.ts").read_text(encoding="utf-8")
    for x in (
        "Previous Page",
        "Next Page",
        "Current page and total pages",
        "actualPageCount",
        "preferredPageCount",
        "beforeunload",
    ):
        assert x in ui + preview
    assert (
        "localVersion" in coordinator
        and "confirmedVersion" in coordinator
        and "Conflict" in coordinator
    )
