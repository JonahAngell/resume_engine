# Plan: AI suggestions that work the highlighted keyword into the resume

> **Status: implemented.** Open decisions 1 to 3 went with the recommendations. Decision 4 (coach prompt) is still open. Endpoints and guardrails are documented in `ai_overview.md`.

**Goal.** When a user clicks a yellow (suggested) keyword such as "A/B Testing", the AI should:

1. Look across the whole resume and propose wording that **includes the keyword** in one or more existing bullets.
2. Offer to **write a new bullet** that uses the keyword, under a role or project the user picks.

Nothing saves until the user accepts, as today.

---

## 1. Why it doesn't work today

| # | Cause | Where |
|---|---|---|
| 1 | The prompt never asks for the keyword. The `keyword_rule` for non-guarded terms says *"You may use the words X only if the bullet already shows that work"*. Combined with "Every fact must come from the original bullet", the model reads this as "don't add it", so it rewords for tone and leaves the keyword out. | `backend/app/ai_variants.py` `suggest_variants` (the `guard` string), `VARIANT_SYSTEM` |
| 2 | No check that drafts contain the keyword, so drafts without it are shown as valid. | `ai_variants.filter_drafts` |
| 3 | Even the `align` goal only says "where the bullet already supports it". | `ai_variants.GOALS` |
| 4 | The popover only offers "Generate AI revision" when the deterministic matcher found a bullet with token overlap (`_placement_options`, top 2 only). If nothing overlaps, the user only sees "Not found in this resume yet". The AI is never asked to look at the rest of the resume. | `job_match._placement_options`, `frontend/src/match/MarkPopover.tsx` |
| 5 | Every AI path rewrites an existing placement (`/bullet-placements/{id}/ai-variants`). There is no AI path that creates a bullet. | `main.py`, `SuggestVariantDialog.tsx` |

The fact guard itself is not the blocker. `drop_reason` already lets an allowed (non-guarded) keyword through. I checked: "A/B Testing" is `methodology` and a draft adding it passes. Only tools, credentials, degrees and experience durations are blocked, and that should stay.

---

## 2. Design

### 2a. Keyword mode for single-bullet drafts (small change, fixes #1–#3)

- `AiVariantRequest` gets `incorporate_keyword: bool = False`. The popover and Requirements tab send `true` when the user opened the dialog from a suggested keyword.
- In `suggest_variants`, when `incorporate_keyword` is set and the keyword is allowed:
  - Replace the guard with: *"Every draft must include the exact phrase "{keyword}". Work it in where it describes the work this bullet states. If it cannot honestly fit, return an empty drafts list and set `fits` to false with a one-line reason."*
  - Add `fits: bool` and `reason: str` to `VARIANT_SCHEMA`.
- `filter_drafts` gets a `require_keyword` flag. In keyword mode, drafts without the keyword (`_contains`, plus `DICTIONARY.mentions` for synonyms like "A/B tests") are dropped with the new reason `missing_keyword`.
- Bump `VARIANT_PROMPT_VERSION` to `"2"`. The cache key already includes the version; add `incorporate_keyword` to it as well.
- `VariantSuggestions` gets `fits` / `reason`, so the dialog can say "The AI doesn't think A/B Testing fits this bullet: …" instead of "No safe rewrites."
- Guarded categories keep their current behaviour. Tools still go to Add to Skills.

### 2b. Resume-wide keyword assist (new, fixes #4 and #5)

New module `backend/app/ai_keyword.py`, built like `ai_coach.py`. It reuses `drop_reason`, `job_tool_terms`, `remember_issued`, `scrub`/`redact_job` and the `complete=` test hook.

**Endpoint.** `POST /api/compositions/{cid}/ai-keyword-assist`
Request: `{ job_id, keyword, requirement, category }`. The server loads all placed bullets and their parent entries (role, org, dates, project name). It never trusts text from the client.

**Prompt input.** The keyword, the requirement, the posting, and a numbered list of placed bullets grouped under their parent entry (cap at `MAX_BULLETS = 40`, as in the coach). The deterministic `_placement_options` candidates are marked as "likely fits" hints.

**Model output.**
```json
{
  "revisions": [{ "bullet": 7, "body": "...", "rationale": "..." }],
  "new_bullets": [{ "parent": 2, "body": "...", "rationale": "..." }],
  "no_fit_reason": ""
}
```
- At most 3 revisions (one draft per bullet; the existing dialog can produce more angles for a single bullet).
- At most 2 new bullets, each tied to a numbered parent entry.

**Server-side validation.**
- Revisions: `drop_reason(body, original_bullet, keyword, category, job_terms)` plus `require_keyword`. The bullet number must map to a real placement.
- New bullets: there is no single original, so the **fact source is the parent entry's full text** (title, org, and all of its bullets). Run `drop_reason` with that text as `original` and skip the length/unchanged checks. The keyword is required. This blocks invented numbers, tools and proper nouns while still allowing a new sentence about work the role plausibly involved.
- Unknown parent numbers, or parents that aren't experience/project/leadership entries, are dropped.
- `remember_issued` keyed by placement id for revisions, and by `new:{parent_id}` for new bullets, so accept can record honest AI provenance.

**Accepting.**
- Revision: the existing `/bullet-placements/{id}/ai-variants/accept` endpoint, unchanged.
- New bullet: extend `BulletCreateAndPlace` with optional `job_id`, `source` (`draft|edited|own`) and `model`. In `create_and_place`, look up `issued_draft("new:{parent_id}", body, job_id)` and write the provenance columns from migration 024 on the new default variant. No migration is needed if the columns live on `bullet_variants`; verify this during the build.

### 2c. Frontend

- **`AssistRequest`** (`match/types.ts`) gets `{ kind: "keyword"; keyword; requirement; category }`.
- **`MarkPopover.tsx`**: for every *suggested* keyword whose category isn't guarded, show a primary **"Work into resume"** button, even when `item.rewrites` is empty. That replaces the dead-end "Not found" hint for these keywords. The existing per-bullet "Generate AI revision" buttons remain and now send `incorporate_keyword: true`.
- **New `KeywordAssistDialog.tsx`** (built on `ModalShell`, styled like `SuggestVariantDialog`):
  - Header: keyword and requirement.
  - **"Revise an existing bullet"**: each card shows the current bullet, the proposed wording with the keyword highlighted (reuse `highlightSegments`), an Edit toggle, and "More options…", which opens `SuggestVariantDialog` for that placement in keyword mode.
  - **"Add a new bullet"**: each card shows the draft plus a parent picker (preselected to the model's choice, listing the resume's entries) and an Edit toggle.
  - A short honesty line above Accept: *"Only use this if you actually did {keyword}. It will appear on your resume as written."*
  - Accept calls the right endpoint, then `onApplied(state)`. The match re-runs and the keyword turns green.
  - Empty/failed states: show `no_fit_reason` / `detail`, plus a "Write a new bullet myself" option prefilled with the keyword.
- **`App.tsx`**: render `KeywordAssistDialog` for `assist.kind === "keyword"`.
- **Requirements tab `RowActions`** and **Coach cards**: add the same "Work into resume" action for missing non-tool keywords, so all three entry points work the same way.

---

## 3. Build order

1. **Keyword mode in `ai_variants`** (2a) + tests. Small, ships the most visible fix on its own.
2. **`ai_keyword.py` + endpoint** (2b), with the `complete=` stub tests.
3. **New-bullet accept with provenance** (`BulletCreateAndPlace` extension).
4. **Frontend**: types → popover button → `KeywordAssistDialog` → App wiring → Requirements/Coach entry points.
5. Rebuild `frontend/dist`, update `README.md` / `ai_overview.md` / `docs/ai_suggestions_blueprint.md` invariants (the "rewrite only the given bullet" line changes).

## 4. Tests

- `tests/test_ai_variants.py`: keyword mode drops drafts missing the keyword; synonyms count; guarded categories still refuse; `fits=false` passes through; cache key separates the two modes.
- `tests/test_ai_keyword.py` (new): revisions map to real placements; invented numbers/tools/proper nouns are dropped in both revisions and new bullets; new bullet with unknown parent is dropped; caps are respected; unavailable/rate-limited/invalid statuses.
- Integration (`test_ai_variants_integration.py` style): accepting an issued new bullet stores `ai_generated=true`; an edited one stores `false` but keeps model/job; another user's composition or job returns 404.
- `test_job_match.py`: after accepting, the keyword shows as found.
- Frontend contract test (as in `test_editing_library_ui_contract.py`): popover shows "Work into resume" for suggested methodology/domain keywords and not for tools.

## 5. Open decisions

1. **Metric placeholders in new bullets.** New bullets read weaker without numbers, but the guard forbids invented ones. Option: allow `[metric]` / `[X%]` placeholders that the dialog highlights and blocks Accept until they're replaced. *Recommendation: yes.*
2. **Honesty confirmation.** Choose between a passive note (above) and a required checkbox ("I have done this"). *Recommendation: passive note. The user already chooses and edits each draft.*
3. **Soft-skill keywords** ("communication", "ownership"): include them in "Work into resume", or limit it to methodology/domain/responsibility? *Recommendation: include them, but rank them lower.*
4. **Coach prompt.** The coach has the same "never add" stance, so it rarely brings keywords in. Updating `COACH_SYSTEM` to prefer keyword-bearing rewrites is a natural follow-up, but it's out of scope here.
