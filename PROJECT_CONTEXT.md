# Resume Engine Project Context

## Purpose

This document records current functional, security, and architectural contracts. Source, migrations, tests, and deployment configuration are authoritative.

## Application

<!-- RESUME-ENGINE-VERSION:PROJECT-CONTEXT:BEGIN -->
**Current version:** v0.1.36
<!-- RESUME-ENGINE-VERSION:PROJECT-CONTEXT:END -->

Phase 2E completes current-user-scoped Library search and composition lifecycle management, including blank creation, metadata editing, archive/restore, timestamps, revision preview, conflict reload, and independently normalized duplication.

## Identity and authorization

StudioShare Launch MyID remains the non-local identity source. APP_ENV=local alone enables DEV_USER_* identity. OPA remains default deny with only GET /health public. Every repository operation derives user ownership server-side; client user_id values are not accepted.

## Data and migrations

Ordered additive migration 004_phase2_historical_library.sql expands education and historical metadata, composition settings, custom sections, custom entries, composition custom-section selection, and immutable composition revisions. Migration 005_phase2a_seed_selections.sql non-destructively backfills education and interest selections for seed-imported compositions only. Migration 006_phase2b_seed_selections.sql non-destructively backfills tool-group and historical selections for seed-imported compositions only. Migration 007_phase2c_bullet_selections.sql deterministically backfills seed composition bullet selections and adds lookup indexes. Migration 008_phase2d_custom_section_guard.sql additively replaces the Phase 2 ownership function so composition custom-section links are validated without referencing a nonexistent user_id column; existing triggers continue to enforce same-user relationships. Migration 009_phase2g_resume_metadata.sql additively stores display title, target company, and target role and enriches immutable revision snapshots with composition metadata. Existing migrations are unchanged. Existing render_payload values remain readable for migration compatibility. Migration 010_phase2j_reusable_bullet_placements.sql additively introduces generalized resume-specific bullet destinations, wording snapshots, ownership guards, usage indexes, and revision relationship snapshots. Migration 011_phase2k_library_management.sql additively introduces normalized user-owned tags and bullet-tag associations while retaining legacy array columns for compatibility. Migration 012_phase2l_date_sorting_metadata.sql additively introduces preferred page length, resume-level date format, section sort modes, structured custom-entry dates, validation constraints, and enriched revision snapshots. Migration 013_phase3b_placement_backfill.sql additively backfills missing historical entry placements from the wording each composition currently renders.

## Editing and rendering

Library records are reusable user-owned content. Phase 2A library forms use explicit Save and Cancel; composition summary selection, interest inclusion, and interest layout remain autosaved with optimistic revision checks. Composition autosaves retain optimistic revisions and return 409 on stale writes. Each successful composition save records an immutable revision snapshot. Restoring history creates a new revision and leaves prior history intact. backend/app/templates/resume.html remains the only preview/PDF template and supports dynamic section order, optional contact values, interest layouts, and escaped custom sections.

## Ownership

Foreign and absent records retain equivalent not-found behavior. Phase 2C application routes validate the complete parent, bullet, variant, destination, and composition chain before mutation; database triggers remain defense in depth. Migration 003 guards Phase 1 relationships; migration 004 adds guards for custom entries, custom-section composition links, and composition revisions. Search is current-user scoped and combines summaries, education, interests, compositions, tools, historical entries, wording variants, custom sections, custom entries, and supported tags into one deterministic paginated result stream.

## Deployment

Launch Login and permissions remain dashboard responsibilities. The app reads Launch-injected database/API variables. No secret or populated environment file is packaged.

## Tests

Phase 1 identity, OPA, renderer, version, and tooling tests remain. Phase 2 adds migration/static contracts plus tests/test_phase2_integration.py coverage for populated Phase 1D migration, exact revision snapshots, restoration, archives, search isolation, stale writes, and new ownership relationships. tests/async_test_utils.py provides a Psycopg-compatible Windows selector event loop for database integration tests. PostgreSQL integration tests require TEST_DATABASE_URL and schema create/drop permission.

## Known limitations

Phase 2A covers profile, summary, education, and interest authoring. Phase 2B covers tools and historical entries. Phase 2C covers bullet and wording-variant authoring and per-composition selection. Phase 2D covers custom-section authoring and global section ordering. Phase 2E provides complete search UI and composition management. Phase 2F presents composition lifecycle management through the Home and Bin experience. Phase 2G adds server-generated collision-safe default names plus optional display title, target company, and target role metadata without printing target metadata on the resume. Phase 2H adds the branded editing top bar, resizable and collapsible desktop workspaces, preview zoom and fullscreen controls, and an independent mobile Editor/Live View preference using browser-local presentation state. Phase 2J adds active-only reusable bullet selection, atomic create/insert/remove/replace/reorder operations, generalized destination ownership, and wording-preserving usage snapshots. Phase 2I restructures composition editing into collapsible section containers, keeps Profile fixed first, and separates local collapse preferences from persisted visibility. Phase 3b completes keyboard-accessible ordering for sections, entries, and placed bullets. Phase 2K adds normalized tag authoring, standalone bullet creation, deterministic management pagination, bulk management operations, and usage status navigation APIs. Legacy array tag columns remain for compatibility and tags remain excluded from render payloads. Phase 2N adds editor-session undo/redo for committed Resume Details and preference commands, guarded keyboard shortcuts, stack isolation/reset behavior, modal focus containment/restoration, and editor interaction accessibility improvements. Phase 2N does not claim final full-application certification. Phase 2L adds canonical structured-date ordering and adjacent same-company heading suppression in shared preview/PDF preprocessing, composition preferences, expanded Home/Bin metadata search, and structured custom-entry storage. Controlled custom-section layouts do not permit arbitrary HTML. Launch permission configuration cannot be committed as source.

## Maintenance

Update this document when identity sources, OPA exceptions, database schema/migrations, ownership predicates, routes, renderer contracts, security tests, known limitations, or current version change.

Phase 3A adds the branded editor shell, toolbar rename, visibility switches, drag handles, collapsible Resume Details, and the initial Add Bullet affordance. Phase 3b replaces selection lists with composition entry cards, renders resume-specific bullet placements as rows, adds the Add Entry workflow, and records that rendered bullets come from placements. Education and tool-group bullet template support remain Phase 3d prerequisites.

Phase 2O adds the permanent standalone Reusable Library workspace, list/card preference, details/variants/usage management, responsive navigation, bulk actions, standalone creation, and expanded picker workflow integration over the Phase 2J/2K contracts.

### Phase 2P release certification

Phase 2P adds evidence-driven traceability and release records, unified SVG primary navigation/document icons, approved brand tokens, visible focus, forced-colors, and reduced-motion safeguards. Static source checks remain supplemental. Unexecuted browser, database, PDF, screenshot, and assistive-technology checks remain pending in `RELEASE_CERTIFICATION.md`.

### Hotfix 3b.1

Hotfix 3b.1 preserves preferred page length, date format, and section sort modes across composition actions and revision restore. Structured dates are retained and formatted during shared preview/PDF preprocessing. The editor uses the shared MonthYearField for reachable structured-date creation, and manual or automatic sort modes reach the rendering path. The dead-end in-editor Library branch was removed; Edit in Library and Add Section remain focusable, inactive controls with a Phase 3b.2 tooltip.

#### Phase 3b.2

Phase 3b.2 makes the standalone Reusable Library the authoring surface for reusable entries and bullets. Section-scoped Entries and Bullets views remember the browser preference; editor deep links force Entries. Shared LibraryEntryForms use MonthYearField for structured dates. Edit in Library and Add Section store a resume-engine-return-target, and the Library provides return-to-resume navigation that reloads the composition and restores editor state. The obsolete in-editor Library management surface is no longer used. Archiving an entry preserves existing resume rendering and warns when active resumes use the record.

#### Phase 3c

Phase 3c corrects composition preference loading and archive SQL, expands revision restoration and adds an owner-scoped revision render route. It consolidates dialogs through a portal-based ModalShell, removes browser prompt and confirm calls, restores Duplicate and Revision History through More actions, moves pane collapse to the divider, and makes measured preview pages navigable one at a time. Phase 3d rebuilds Add Bullet on ModalShell. The pre-commit hook continues to set the application version.
