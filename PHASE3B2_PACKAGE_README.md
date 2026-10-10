# Resume Engine Phase 3b.2 replacement package

Apply over repository root. This package is based on REVIEW_BUNDLE commit `1692c31a332552cbf45ae6df924ed1b9d407f519`.

## Included

- Standalone Library Entries/Bullets mode, Add New menu, entry detail/create forms, archive warning, and bullet deep-open.
- Shared `LibraryEntryForms.tsx` using `MonthYearField`.
- Editor return-target routing for Edit in Library and Add Section.
- Structured custom-entry date schema fields.
- CSS, contract tests, and project context update.

## Validation performed

- Python syntax compilation for modified backend schema.
- Phase 3b.2 static contract test.
- TypeScript source checked for balanced delimiters with the available package snapshot.

## Required repository validation

```bash
npm run build
pytest -q
npx playwright test tests/resume-layout.spec.ts
```

Database and browser integration require the complete repository and configured services.
