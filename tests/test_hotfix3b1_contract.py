from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_preferences_dates_navigation_contract():
    app=(ROOT/'frontend/src/App.tsx').read_text(encoding="utf-8"); repo=(ROOT/'backend/app/library_repository.py').read_text(encoding="utf-8"); phase=(ROOT/'backend/app/phase2l.py').read_text(encoding="utf-8")
    assert 'preferred_page_length' in repo and 'section_sort_modes' in repo
    assert 'date_format="long"' in phase and 'display_date(row,date_format)' in phase
    assert (ROOT/'frontend/src/MonthYearField.tsx').exists()
    month=(ROOT/'frontend/src/MonthYearField.tsx').read_text(encoding="utf-8"); assert 'Year only' in month and '03/2024' in month
    assert 'setTab("library")' not in app
    # Phase 3b.2 replaced the inactive editor Library control with a
    # working return-target flow.
    assert "openLibraryFromEditor" in app
    assert "resume-engine-return-target" in app
    assert "resume-engine-library-target" in app
