from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase2h_shell_and_topbar_contract():
    source = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    for text in (
        "editing-topbar",
        "editing-brand",
        "Home",
        "Save",
        "Undo",
        "Redo",
        "Export PDF",
        "topbar-status",
        "workspace-splitter",
    ):
        assert text in source
    assert 'className="export-action"' in source
    assert 'runHistoryAction("undo")' in source
    assert 'runHistoryAction("redo")' in source
    assert 'aria-keyshortcuts="Control+Z Meta+Z"' in source
    assert "EditorHistory" in source
    assert "Undo is planned" not in source
    assert "Redo is planned" not in source


def test_phase2h_presentation_preferences_are_local_and_independent():
    source = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    for key in (
        "resume-engine-editor-percent",
        "resume-engine-editor-collapsed",
        "resume-engine-preview-collapsed",
        "resume-engine-mobile-workspace",
        "resume-engine-preview-zoom",
    ):
        assert key in source
    assert "localStorage" in source
    assert (
        "aria-valuenow" in source and "ArrowLeft" in source and "ArrowRight" in source
    )


def test_phase2h_responsive_preview_contract():
    source = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/resume-print.css").read_text(encoding="utf-8")
    for text in (
        "Editor",
        "Live View",
        "Zoom out",
        "Zoom in",
        "Expand preview",
        "Show editor",
        "Show preview",
    ):
        assert text in source
    assert "@media (max-width: 900px)" in css
    assert ".mobile-editor .stage" in css and ".mobile-preview .editor" in css
    assert "var(--branch-blue)" in css and "var(--safety-red)" in css
    assert "8.5in" in css and "11in" in css
