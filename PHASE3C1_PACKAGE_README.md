# Phase 3c.1 package

Source fingerprint: d22c0e081c292a530bb867ea8864487bbc113198

## Included changes

- Phase 3c UI cleanup: autosaving metadata fields, Home dialogs, revision history rendering, and real Library bulk/variant editors.
- Retired promptDialog, BulletVariantSelection, select_bullet_variant, and PUT /bullet-variant.
- Added additive migration 014 for all five bullet parent columns, generated parent_type, ownership checks, and indexes.
- Added placement-only resume hydration helper, ID-based placement application, duplicate response mapping, and destination inclusion validation.
- Added resume schema/template support for education, tool-group, interest, and custom-entry bullets.
- Corrected composition materialization preferences and archive RETURNING SQL.
- Strengthened the Phase 3c prompt contract.

## Apply

1. Extract this ZIP at the repository root, preserving paths.
2. Review migration `backend/migrations/014_phase3c1_bullet_ownership.sql` against a disposable PostgreSQL schema.
3. Run `npm --prefix frontend run build`.
4. Run `pytest -q tests/test_phase3c_contract.py tests/test_phase2j_contract.py tests/test_phase2k_contract.py tests/test_render_api.py`.
5. With `TEST_DATABASE_URL` set to a disposable database, run the Phase 2J/3c integration tests.

## Validation performed

- Python modules compiled with `python -m compileall -q backend/app`.
- Source scans found no `promptDialog(` calls and no active `/bullet-variant` route references.

## Validation not performed

- Frontend TypeScript build was not run because a TypeScript compiler was unavailable in the execution environment.
- PostgreSQL migrations and integration tests were not run because no disposable `TEST_DATABASE_URL` was available.
- Browser, PDF, screenshot, and assistive-technology validation were not run.
