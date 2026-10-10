## Resume Engine Update Request Template

Use this template for feature work, bug fixes, UI adjustments, refactors, performance changes, database or API work, imports or exports, audit-rule changes, and documentation updates.

Complete every relevant section. Use `Not applicable` when a section does not apply. Do not delete safeguards merely to shorten a request. For a narrow, low-risk update, keep the same headings but answer them concisely.

---

# 1. Title

**Request type:**

- [ ] New feature
- [ ] Bug fix
- [ ] UI or CSS adjustment
- [ ] Performance improvement
- [ ] Database or API change
- [ ] Refactor
- [ ] Export or import change
- [ ] Audit logic or business-rule change
- [ ] Documentation only
- [ ] Other:

**Title:** [Short, specific outcome-oriented title]

**Risk classification:**

- [ ] Low: localized presentation or behavior change with no persisted-data, API, authorization, or business-rule impact
- [ ] Medium: state, workflow, import/export, or cross-module behavior change with bounded impact
- [ ] High: database, migration, authorization, security, destructive operation, source-of-truth, or material audit-rule change

---

# 2. Implementation Contract

This section is the controlling summary. Detailed sections below may clarify it but must not contradict it.

**Goal:**  
[One or two sentences describing the required outcome.]

**Expected files allowed to change:**

- [List only files that current evidence indicates are likely to require modification.]

**Required generated artifacts:**

- [List generated files that must be rebuilt and delivered, or state `None`.]

**Conditional files:**

- [Example: `css/manifest.json` only if changed by the CSS build.]
- [Example: `PROJECT_CONTEXT.md` only if a documented maintenance trigger occurs.]

**Behavior that must remain unchanged:**

- [List the most important protected workflows, contracts, and business rules.]

**Definition of done:**

- [Summarize the essential observable results.]
- [Summarize the minimum required validation.]
- [State the requested deliverable format.]

**Blocking assumptions or decisions:**  
[List only matters that could cause an incorrect business rule, unsafe migration, security issue, wrong source of truth, irreversible change, or major regression. If none, state `No known blocking assumptions or decisions.`]

**Implementation flexibility:**  
The desired behavior and acceptance criteria are mandatory. Any implementation approach described in this request is a preference unless explicitly labeled `Required implementation`. If current source evidence shows that a preferred approach is unsafe or incorrect, use the smallest safe alternative and explain the deviation.

---

# 3. User-visible Problem

**Users or roles affected:**  
[Who experiences the problem?]

**Workflow affected:**  
[Where in the user journey does it occur?]

**Current observable behavior:**  
[Describe what a user can directly observe. Do not mix diagnosis into this field.]

**Where it occurs:**  
[Page, panel, route, report, export, import, or process.]

**Frequency:**

- [ ] Always or reproducibly
- [ ] Intermittently
- [ ] Data-dependent
- [ ] Environment-dependent
- [ ] Unknown

**Trigger or reproduction sequence:** 1. 2. 3.

**Business or technical impact:**  
[Explain the consequence without overstating unverified risk.]

**Screenshot, recording, log, or sample attached:**

- [ ] Yes
- [ ] No
- [ ] Not applicable

---

# 4. Verified Source Evidence

Separate facts directly established by current authoritative materials from hypotheses that still require validation.

## 4.1 Source Authority

Use sources in this order unless the request explicitly states otherwise:

1. Most recently attached current files and current-request instructions
2. `PROJECT_CONTEXT.md`
3. `PROJECT_TREE.txt`
4. Current screenshots, logs, console output, recordings, and Inspect Element details
5. Explicitly identified enterprise knowledge source
6. Related current source files and established project patterns
7. Earlier conversation context
8. Historical patches or archived versions only when explicitly requested

**Authoritative materials attached:**

- [List each current file, screenshot, log, or sample.]

**Important version instruction:**  
Use only the most recently attached current files as implementation inputs. Do not substitute archived files, prior-conversation copies, generated aggregates, repository-history versions, or enterprise copies unless explicitly directed.

## 4.2 Verified Facts

List only facts directly supported by the attached source, runtime evidence, or documentation.

- **Evidence:** [Exact observed behavior, declaration, function call, route, schema, error, or computed value.]  
  **Source:** [File and function/selector/line area, screenshot, log entry, or command output.]
- **Evidence:**  
  **Source:**

## 4.3 Implementation Hypotheses

List likely causes or solution directions that still require confirmation. Do not present them as verified facts.

- **Hypothesis:** [Likely root cause.]  
  **Why it is plausible:** [Evidence that supports but does not prove it.]  
  **How to validate:** [Focused code inspection, computed-style check, runtime state check, test, or command.]

If the root cause is fully proven by current evidence, state why it is verified and omit speculative alternatives.

## 4.4 Unknowns

- [List relevant unknowns.]
- [Mark each as blocking or non-blocking.]

For a non-blocking unknown, follow existing patterns, make the smallest reasonable assumption, and disclose it in the delivery summary.

---

# 5. Desired Behavior

**Required behavior:**

- [Describe outcomes, not code edits.]
- [State relevant state transitions and boundary behavior.]

**Expected user flow:** 1. 2. 3.

**Data or business rules, if applicable:** 1. 2. 3.

**Source of truth:**  
[Identify the authoritative system, field, state object, API response, database record, workbook value, or user action. Do not assume Workday or SAP is authoritative unless explicitly established.]

**Null, blank, duplicate, invalid, legacy, or missing-value behavior:**  
[Specify only cases relevant to this update.]

**Error behavior:**  
[Describe required user-facing and diagnostic behavior, or state `No new error path is introduced.`]

**Preferred implementation, if any:**  
[Optional. Describe a maintainable direction without making it mandatory.]

**Required implementation, only when necessary:**  
[Use only when a specific implementation is required by architecture, compatibility, security, data integrity, or an explicit project constraint. Otherwise state `Not specified.`]

---

# 6. Acceptance Criteria

Keep this list concise and non-duplicative. Each criterion should describe one independently observable result. Combine closely related presentation details into one criterion and place procedural checks in the Validation Plan instead.

Recommended target:

- Narrow or low-risk update: 5 to 10 criteria
- Medium-risk update: 8 to 15 criteria
- High-risk update: only as many as needed to cover distinct business, security, migration, and recovery outcomes

1. [Primary user-visible result.]
2. [State or data result.]
3. [Boundary or error condition.]
4. [Key preserved behavior.]
5. [Build or deployable-artifact requirement, if relevant.]
6. [Accessibility or responsive result, if relevant.]
7. [No unintended persistence, API, database, or authorization change, if relevant.]

Do not create separate criteria that merely restate the same resolved style, value, or state on multiple elements unless those elements can fail independently.

---

# 7. Expected, Review-only, and Protected Files

These categories are strict.

## 7.1 Files Allowed to Change

Only files in this list may be modified without first demonstrating a verified technical requirement.

- `[path]`  
  **Expected responsibility in this update:** [Why modification may be necessary.]

## 7.2 Required Generated Artifacts

Generated files may be included only when they are required deployable outputs of modified source files.

- `[path]`  
  **Generation command/source:** [How it is produced.]

Do not edit generated artifacts manually unless the project explicitly defines them as editable.

## 7.3 Review-only Files

These files may be inspected for dependencies, contracts, cascade, load order, documentation, or validation, but must not be changed unless new evidence proves that a change is technically required.

- `[path]`  
  **Reason for review:**

If a review-only file must change:

1. State the verified reason before expanding scope.
2. Explain why the change cannot safely remain in an allowed file.
3. Add the file to the modified-file list in the delivery summary.

## 7.4 Protected Files and Areas

These files or areas must not change as part of this request unless the request is revised because of a blocking technical requirement.

- `[path or area]`
- APIs: [protected routes/contracts]
- Database: [protected tables, migrations, or state]
- Authentication/authorization: [protected behavior]
- Dependencies/toolchain: [protected behavior]

## 7.5 Touchpoints to Inspect

List functions, selectors, routes, tables, events, scripts, or modules that may influence the change without implying that every containing file may be modified.

- Functions:
- Selectors/components:
- Routes/API contracts:
- Tables/schema:
- Events/state transitions:
- Entry point/load order:
- CSS source units/build order:

---

# 8. Technical Constraints

- Preserve existing architecture, folder structure, naming conventions, coding style, contracts, and deployment model.
- Make the smallest safe change that satisfies the desired behavior and acceptance criteria.
- Do not introduce unrelated refactoring, modernization, optimization, framework conversion, or dependency changes.
- Reuse existing utilities, renderers, state, services, routes, and patterns where safe.
- Preserve public signatures, IDs, data attributes, DOM contracts, API contracts, database contracts, accessibility, and script load order unless a change is explicitly required.
- Do not add global state when existing state or local scope is sufficient.
- Do not use placeholders such as `existing code unchanged` in replacement files.
- Do not invent file contents, functions, selectors, routes, data, behavior, or test results.
- Do not change a review-only or protected file merely to match an expected package tree.
- Do not expose or package secrets, tokens, private keys, production connection strings, or populated `.env` files.
- Never claim that a command, test, browser check, deployment, or measurement passed unless it was actually performed.

**Project-specific constraints:**

- [Classic script load-order requirements.]
- [CSS source/build requirements.]
- [Database transaction/migration constraints.]
- [HRIS audit business-rule constraints.]
- [Import/export format constraints.]
- [Performance constraints only if performance is in scope.]

---

# 9. Regression Matrix

Organize regression protection by risk. Do not request every possible test.

## 9.1 High-risk Contracts

Test these whenever they are affected. If not affected, state `Not applicable`.

- **Persisted data / source of truth:** [What must not be corrupted or reassigned?]
- **Authorization / security:** [What capability checks must remain intact?]
- **Database / migration:** [What schema and existing-data guarantees must hold?]
- **Audit business rules:** [What comparison, population, effective-date, null, duplicate, or exception rules must remain exact?]
- **Destructive or irreversible behavior:** [What recovery or rollback requirement applies?]

## 9.2 Medium-risk Workflows

- **State and navigation:** [Load, switch, save, autosave, refresh, back/forward.]
- **Cross-module behavior:** [Dependent renderers, wrappers, services, exports, imports.]
- **API/import/export contracts:** [Request, response, workbook, CSV, JSON, or HTML behavior.]
- **Generated outputs:** [Build products and manifest/cascade behavior.]

## 9.3 Low-risk Presentation and Interaction

- **Primary UI path:**
- **Responsive layout:**
- **Keyboard and focus behavior:**
- **Loading, empty, error, and disabled states:**
- **Theme/contrast/forced-colors behavior, if relevant:**

## 9.4 Explicitly Unaffected Areas

- [List adjacent workflows that current evidence shows do not need regression testing.]

---

# 10. Validation Plan

Request only validation that is relevant and realistically executable with the available files and environment.

## 10.1 Required Before Delivery

Select focused checks based on changed files and risk:

- [ ] Syntax or type validation for modified code
- [ ] Relevant build or generated-artifact check
- [ ] Existing targeted automated tests
- [ ] File-path, import, reference, and load-order review
- [ ] Scoped diff and whitespace check
- [ ] Package integrity and package-content check
- [ ] Focused static contract review

**Exact commands:**

```bash
# Add only commands supported by the current repository.
```

## 10.2 Focused Runtime or Manual Validation

List the smallest set of runtime checks that proves the acceptance criteria and highest-risk regressions.

1. [Primary success path.]
2. [Most important state transition or boundary case.]
3. [Highest-risk preserved workflow.]
4. [Responsive/accessibility check if the UI changed.]

## 10.3 Conditional Validation

Run only if the implementation touches the corresponding area:

- Database or migration validation
- API request/response inspection
- Import/export sample validation
- Browser computed-style inspection
- Performance measurement against an explicit baseline
- Deployment smoke test
- Accessibility tooling

## 10.4 Evidence Rule

For every reported validation:

- Provide the exact command or browser action.
- Provide the actual result.
- Use `Passed` or `Verified` only when the check was performed successfully.
- Use `Failed` when it was performed and failed.
- Use `Not performed` when the environment or supplied files did not permit the check.
- Provide the exact follow-up command or manual step for any important check not performed.
- Do not infer browser, API, database, deployment, performance, or accessibility results from static source review alone.

---

# 11. Documentation Determination

Review `PROJECT_CONTEXT.md` against its maintenance triggers.

Update `PROJECT_CONTEXT.md` only if the implementation changes one or more of the following:

- Application version or technology stack
- Directory structure or documented file responsibility
- Database schema or migration sequence
- New, removed, or renamed JavaScript functions
- Current priorities or known technical debt
- Coding standards or architectural constraints

**Expected determination before implementation:**

- [ ] Update expected
- [ ] Update not expected
- [ ] Cannot determine until implementation

**Reason:**  
[Explain based on the proposed scope.]

**Packaging rule:**  
If a maintenance trigger occurs, update the complete `PROJECT_CONTEXT.md` and include it in the deliverable. Do not update or package `PROJECT_CONTEXT.md` merely because code changed.

---

# 12. Deliverable

**Requested format:**

- [ ] Full replacement files in a ZIP package
- [ ] Modified files only in a ZIP package
- [ ] Single patch file
- [ ] Analysis and implementation plan only
- [ ] Documentation update only
- [ ] Other:

**Preferred package name:**  
`[descriptive-package-name].zip`

## 12.1 Actual-change Packaging Rule

The initial expected file list is a planning aid, not a required package tree.

Include only:

- Files actually modified to implement the accepted behavior
- Required generated artifacts produced from those modifications
- `css/manifest.json` or equivalent only if the build actually changes it
- `PROJECT_CONTEXT.md` only if a documented maintenance trigger occurs
- Migration files only when a database change is explicitly in scope and implemented

Exclude:

- Unchanged review files
- Aggregate review text files
- Screenshots, logs, and temporary files
- Historical patches and prior packages
- `node_modules`
- Secrets, credentials, tokens, private keys, production connection strings, or populated `.env` files
- Files changed only to make the package resemble the forecast

Preserve project-relative paths. Do not flatten directories.

**Illustrative expected package, if the preferred approach is sufficient:**

```text
[package-name].zip
├── [modified source]
└── [required generated artifact]
```

The final package may differ from this illustration when actual verified changes differ. Explain every difference.

---

# 13. Evidence-based Delivery Summary

Keep the delivery summary concise and use these headings:

- **Root cause:** Verified cause, or remaining hypothesis if runtime confirmation was not possible
- **Implementation:** What changed and why
- **Modified source files:** Actual modified source files only
- **Generated artifacts:** Actual regenerated files only
- **Conditional files:** Whether manifest, migration, lockfile, or `PROJECT_CONTEXT.md` changed and why
- **Validation performed:** Exact commands/actions and actual results
- **Validation not performed:** Important checks not completed and exact follow-up steps
- **Assumptions:** Non-blocking assumptions used
- **Known risks or limitations:** Remaining uncertainty or environment limitation
- **Scope confirmation:** Explicit confirmation of protected areas not changed
- **Application steps:** Exact extraction, build, migration, or deployment steps that apply
- **Verification steps:** Focused user/runtime checks
- **Download:** Link to the requested artifact

Do not repeat the entire feature request in the delivery summary.

---

# 14. Detailed Reference Appendix, if Needed

Use this appendix only when detail would distract from the controlling implementation contract. Omit subsections that are not relevant.

## 14.1 Current-version Fingerprint

Capture a repository revision and working-tree status whenever Git metadata is available:

```bash
printf '===== REPOSITORY FINGERPRINT =====\n'
git rev-parse HEAD
git status --short
```

Capture hashes for authoritative implementation inputs:

```bash
printf '\n===== AUTHORITATIVE FILE HASHES =====\n'
sha256sum \
  path/to/file-one \
  path/to/file-two \
  PROJECT_CONTEXT.md
```

For a combined review bundle, place the fingerprint before file contents:

```bash
{
  printf '===== REPOSITORY FINGERPRINT =====\n\n'
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf 'Commit: '
    git rev-parse HEAD
    printf '\nWorking tree status:\n'
    git status --short
  else
    printf 'Git metadata unavailable\n'
  fi

  printf '\n===== AUTHORITATIVE FILE HASHES =====\n\n'
  sha256sum \
    path/to/file-one \
    path/to/file-two \
    PROJECT_CONTEXT.md

  for file in \
    path/to/file-one \
    path/to/file-two \
    PROJECT_CONTEXT.md
  do
    if [ ! -f "$file" ]; then
      printf 'ERROR: required file not found: %s\n' "$file" >&2
      exit 1
    fi
    printf '\n===== BEGIN FILE: %s =====\n\n' "$file"
    cat "$file"
    printf '\n\n===== END FILE: %s =====\n' "$file"
  done
} > implementation-review.txt
```

**Fingerprint rules:**

- Record the fingerprint when the request bundle is created.
- Do not modify a file solely because its hash appears in the request.
- In the delivery summary, state whether implementation used the supplied fingerprinted versions.
- If a replacement file no longer matches the supplied input revision because the user provided a newer authoritative version, use the newer version and disclose the change.
- Do not treat a dirty working tree as an automatic blocker, but identify unrelated existing changes before overwriting files.

## 14.2 Function, Selector, Route, and Schema Inventory

- Functions:
- Selectors/components:
- Routes:
- API request/response shapes:
- Tables/columns/constraints:
- Events:
- State properties:
- CSS source units:

## 14.3 Data Examples

**Example input:**

```text

```

**Expected output:**

```text

```

## 14.4 UI Detail

- Affected page/panel:
- Desktop behavior:
- Responsive behavior:
- Overflow/scrolling:
- Loading/empty/error/disabled states:
- Keyboard/focus/accessibility:
- Relevant computed styles:

## 14.5 HRIS Audit Rule Detail

- Source systems and files:
- Source-of-truth field/system:
- Comparison direction:
- Population:
- Effective-date rules:
- Normalization:
- Null/blank handling:
- Duplicate handling:
- Exceptions:
- Regional differences:
- Required Analyst Logic:
- Required Developer Logic:
- Notes:

## 14.6 Database, API, and Migration Detail

- Existing schema and constraints:
- Proposed schema effect:
- Existing-data compatibility:
- Transaction boundaries:
- Authorization:
- Recovery/rollback approach:
- API compatibility:
- Parameterization and sensitive-data handling:

## 14.7 Import and Export Detail

- Input format and sample:
- Sheets/tables/files:
- Headers/columns:
- Types and formulas:
- Blank/duplicate/invalid handling:
- Output format and naming:
- Formatting to preserve:
- Error behavior:

---

## Final Request-quality Check

Before sending the request, confirm:

- [ ] The Implementation Contract is short and controlling.
- [ ] User-observable behavior is separated from diagnosis.
- [ ] Verified facts are separated from hypotheses and unknowns.
- [ ] Desired behavior is stated as outcomes rather than unnecessary code instructions.
- [ ] Acceptance criteria are concise and non-duplicative.
- [ ] Files allowed to change are distinct from review-only and protected files.
- [ ] Validation is focused by risk and executable in the available environment.
- [ ] The request includes a repository commit or file hashes when possible.
- [ ] Documentation triggers were evaluated against `PROJECT_CONTEXT.md`.
- [ ] Deliverable contents depend on actual changes, not the forecast.
- [ ] The requested delivery summary is concise and evidence-based.
