# Resume Engine Phase 3c package

Apply over commit `8c2c37323ef02e9f7558c70547300eb4171e7f3b` while preserving paths. `frontend/src/app-version.ts` is intentionally excluded because the pre-commit hook owns version updates.

Validation completed in the scoped package workspace:

- Python syntax compilation for supplied backend modules.
- TypeScript/TSX syntax transpilation for supplied `.tsx` source files.
- Static search confirms no browser `prompt(` or `confirm(` call remains in `frontend/src`.

Validation still required in the complete repository:

```bash
npm ci
npm run build
pytest -q
TEST_DATABASE_URL=postgresql://... pytest -q tests/test_phase3c_integration.py
npx playwright test tests/resume-layout.spec.ts
```

Use a disposable PostgreSQL database with schema create/drop permission. Review the resulting diff before deployment.
