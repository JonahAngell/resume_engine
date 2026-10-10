
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_phase3c_static_contract():
 app=(ROOT/'frontend/src/App.tsx').read_text(encoding="utf-8"); modal=(ROOT/'frontend/src/ModalShell.tsx').read_text(encoding="utf-8"); fit=(ROOT/'frontend/src/FitIndicator.tsx').read_text(encoding="utf-8"); template=(ROOT/'backend/app/templates/resume.html').read_text(encoding="utf-8"); src='\n'.join(p.read_text(encoding="utf-8") for p in (ROOT/'frontend/src').glob('*.tsx'))
 assert 'createPortal' in modal
 assert 'prompt(' not in src and 'confirm(' not in src and 'promptDialog(' not in src
 assert 'Duplicate…' in app and 'Revision History…' in app
 assert 'compact' in fit
 assert '{% if measure %}' in template and 'resume-show-page' in template
 assert 'editor-collapse-action' not in app and 'BulletPicker' not in app
def test_phase3c_backend_contract():
 library=(ROOT/'backend/app/library_repository.py').read_text(encoding="utf-8"); editing=(ROOT/'backend/app/editing_repository.py').read_text(encoding="utf-8"); main=(ROOT/'backend/app/main.py').read_text(encoding="utf-8")
 for name in ('preferred_page_length','date_format','section_sort_modes'): assert name in library
 assert 'RETURNING *  \n                revision' not in editing
 assert '/revisions/{rid}/render' in main
