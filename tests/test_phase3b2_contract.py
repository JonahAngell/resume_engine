from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_phase3b2_library_contract():
 page=(ROOT/'frontend/src/StandaloneLibrary.tsx').read_text(encoding="utf-8")
 forms=(ROOT/'frontend/src/LibraryEntryForms.tsx').read_text(encoding="utf-8")
 for text in ['Entries','Bullets','resume-engine-library-content-view','Add New ▾','Experience','Project','Education','Leadership','Skill Group','Interest','Custom Section','Custom Entry','used in ${names.length} resume(s)']:
  assert text in page
 assert 'MonthYearField' in forms and 'LibraryEntryForm' in forms
def test_phase3b2_return_contract_and_cleanup():
 app=(ROOT/'frontend/src/App.tsx').read_text(encoding="utf-8")
 for text in ['resume-engine-return-target','resume-engine-library-target','history.pushState','Edit in Library','+ Add Section','returnFromLibrary']:
  assert text in app
 assert 'Editing in the Library from the editor is coming soon.' not in app
 for obsolete in ['function Library(', 'function RecordList(', 'function ToolGroupsEditor(', 'function BulletsEditor(', 'function CustomSectionsEditor(', 'function LibrarySearch(']: assert obsolete not in app
