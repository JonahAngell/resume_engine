# Resume Engine Phase 3b package

Apply the files in this archive over the repository root while preserving paths.

Validation performed in the package workspace:

- Python syntax compilation for supplied `backend/app/*.py`: passed.
- Frontend `App.tsx` esbuild parse/bundle check: passed.
- `tests/test_phase3a_contract.py` and `tests/test_phase3b_contract.py`: 3 passed.

Not executed because the attached review bundle is a scoped source snapshot rather than a complete runnable repository:

- Full frontend TypeScript build and Playwright suite.
- Full pytest suite.
- PostgreSQL migration and integration tests, which require `TEST_DATABASE_URL` and the complete project tree.

Before deployment run:

```bash
npm test
npm run build
pytest -q
npx playwright test
```

Run database integration tests against a disposable PostgreSQL schema before applying migration 013 to any shared environment.
