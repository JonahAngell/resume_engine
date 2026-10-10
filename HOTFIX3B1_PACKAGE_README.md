# Resume Engine Hotfix 3b.1

Apply this archive over repository root while preserving paths. The package was generated from the attached review bundle at commit 59a42e290bcec8d0c6b3995e83bf256e529dd133. No version file was changed.

Validation in the package workspace: Python syntax compilation and hotfix contract tests. Full TypeScript build, full pytest, PostgreSQL integration, Playwright, preview, and PDF checks require the complete repository and TEST_DATABASE_URL.

Run after applying:

```bash
npm test
npm run build
pytest -q
npx playwright test
```
