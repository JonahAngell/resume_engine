# Phase 3b deployment hotfix

## Cause

`backend/app/main.py` uses `EntryCreateWrite`, `composition_items`, and `create_and_include_entry`, but the attached deployment source did not import those names.

## Change

- Added `EntryCreateWrite` to the existing `backend.app.editing_schemas` import.
- Added `composition_items` and `create_and_include_entry` to the existing `backend.app.library_repository` import.
- No routes, schemas, repositories, migrations, or UI behavior were otherwise changed.

## Apply

Extract this archive over the repository root while preserving paths, then rebuild and redeploy the backend image.

## Verify

```bash
python -m py_compile backend/app/main.py backend/app/editing_schemas.py backend/app/library_repository.py
python -c "from backend.app.main import app; print(app.title)"
pytest -q tests/test_phase3b_contract.py
```
