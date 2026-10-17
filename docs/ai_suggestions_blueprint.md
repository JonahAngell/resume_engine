# AI bullet suggestions: review and build blueprint

Status: built on 2026-10-16. `ai_overview.md` describes the shipped behavior; where they differ, follow `ai_overview.md`. Builds on `ai_overview.md` (the current AI review). Where this file names existing code, it was checked against the tree on 2026-10-16.

## Part 1. Review of the draft plan

The plan's shape is right: drafts are generated on demand, nothing is saved until Accept, the change is scoped to one resume, and the free-model gate stays in one place. The problems are mostly places where the plan assumes something the code does not have yet.

### Must fix before building

1. **Migration 021 is taken.** `021_job_keyword_review.sql` exists, and the latest file is `023_resume_variants.sql`. `database.py` records applied migrations by file name, so a second `021_*` file would run, but it would be out of order and confusing (there are already two `020_*` files). Use **`024_bullet_variant_ai_provenance.sql`**.

2. **Accept should not chain two existing endpoints.** `create_variant` (`editing_repository.py:763`) and `replace_placement` (`phase2j_repository.py:124`) each open their own transaction, and `create_variant` takes no composition revision. If the revision check in `replace_placement` fails, the variant has already been committed and is left orphaned in the library. There is already a path that does exactly what Accept needs in one locked transaction: `save_bullet_edit(..., mode="variant")` in `resume_variants.py:584`. It locks the composition at the given revision, inserts a non-default variant with a unique name, points the placement at it, refreshes the snapshot, and rerenders. Extend that function with `name` and provenance arguments rather than composing two calls.

3. **"Partial match" is not a thing in the code.** Preview marks are `kind: "match" | "suggestion"` (`matchMarks.ts`). A suggestion mark is an unfound keyword plus up to two candidate lines from `_placement_options` (`job_match.py`). Define the feature as: *the Suggest button appears on a bullet line that carries a `suggestion` mark.* Skip the `tools` fallback line and `tool-group-*` lines; those are skill rows, not bullets.

4. **The preview has no placement ids.** Lines are tagged `data-bullet-id="{parent}-bullet-{index}"`, a positional id, and `TagSuggestion` only carries `bullet_id` (the library bullet) and that `line_id`. A library bullet can be placed more than once, so `bullet_id` alone does not identify the placement. Add `placement_id` to `_placed_bullets` (`job_repository.py:228`, it already selects from `composition_bullets cb`), carry it through `_bullet_candidates` and `TagSuggestion`, and keep `line_id` for the DOM. The frontend then maps the clicked `line_id` to a `placement_id` from the match response.

5. **Which job?** The plan says "the job selected in Resume Details" and "reads the job from the composition" (`resume_compositions.job_description_id`). But the highlights come from the job the Job Match panel is comparing (`compareJob` in `App.tsx`), and `JobMatchPanel` can compare a job other than `linkedJobId`. If the two differ, the drafts would be written for a job the user isn't looking at. Send `job_id` explicitly in the request (the job whose marks are on screen), check it belongs to the user, and store it as `ai_job_id`. If you want to keep "Resume Details job only", then hide the Suggest button whenever `compareJob.id !== comp.job_description_id` and say why in a tooltip.

6. **Missing tools go to Skills, not to AI.** Most suggestion marks are missing *tools* (the matcher is keyword-driven). The guardrail correctly forbids a rewrite from adding a tool the bullet doesn't show, so AI drafts can't help there. A missing tool is fixed by adding it to Skills, which needs no AI. That flow is in Part 2 under **Skills quick add**. Split the work by keyword type:
   - Tool keywords (`category_for_term(keyword) == "tool"`, or the matcher's best placement for the keyword is a `tool-group-*` line or the `tools` fallback) get **Add to Skills**. They don't get a Suggest chip.
   - Everything else on a bullet line gets **Suggest**. The keyword's category goes into the prompt.
   - For `credential`, `degree`, `experience_duration`, the model may not add the term. Drafts may only sharpen wording toward the requirement. The dialog says: *"Drafts can't add this for you. If it's true, choose Write my own."*
   - For `domain`, `responsibility`, `methodology`, `soft_skill`, the term may appear if it describes what the original bullet already shows.
   - If a tool keyword also has a bullet candidate, the dialog can still show a link to Add to Skills, so the user isn't sent to AI first.

7. **"Goal" is undefined.** Nothing in the code or UI has a goal. Either drop it from v1 or define a small fixed set and put it in the dialog (see Part 2, F2). Free text would be a prompt-injection path into the model and should be avoided.

### Should fix

8. **Provenance clearing must cover every body write, not just `update_variant`.** `save_bullet_edit(mode="overwrite")` also rewrites `bullet_variants.body`, and library import/commit code may too. Do it in the database with a `BEFORE UPDATE` trigger: if `NEW.body IS DISTINCT FROM OLD.body` and the writer didn't set the flag explicitly, clear it. Renames don't touch `body`, so they keep the flag for free.

9. **Decide what "edited before accept" means.** The plan says editing a draft clears the flag, but a draft edited inline in the dialog is still mostly AI text. Recommendation: store `ai_generated = true` only for a draft accepted unchanged. An edited draft stores `ai_generated = false` but keeps `ai_model` and `ai_job_id` so the history isn't lost. "Write my own" stores nothing. Make the trigger clear only `ai_generated`, never the other two columns.

10. **Duplicate copies the body, so it should copy the flag.** `duplicate_variant` makes an identical copy. Copy `ai_generated`, `ai_model`, `ai_job_id` too, otherwise duplicating launders the marker.

11. **Variant name collisions.** `bullet_variants` has `UNIQUE (bullet_id, name)` and `VariantWrite.name` is max 120. Run the model's name through the existing `_unique_name` helper and truncate. Never fail Accept on a name clash.

12. **Overlap with the existing review suggestions.** `ai_review.py` already returns display-only `suggestions` (`requirement`, `resume_quote`, `suggestion`) shown under "Rewrite suggestions" in `JobMatchPanel`. Two different rewrite features will confuse users. Pick one: either route those cards into the new dialog (an "Open in Suggest" button when `resume_quote` matches a placed bullet), or remove them from the review once this ships. The first is cheaper and reuses work.

13. **Temperature 0 gives near-duplicate drafts.** The client always uses temperature 0. Ask for distinct angles in one call (for example: concise, outcome-first, requirement-aligned), then dedupe drafts that are equal to each other or to the original after whitespace and case folding.

14. **Hover doesn't exist on phones.** The plan says hover or focus and tests the dialog at phone width, but not the button. On touch, tapping a suggestion line should show the button; a second tap opens the dialog.

15. **`complete_json` doesn't send the schema.** Per `ai_overview.md`, `use_schema=False` always. Define `VARIANT_SCHEMA` for documentation and parity, but validate with Pydantic and the filters, not with the provider.

16. **Cache drafts.** Free models rate-limit quickly and users will reopen the dialog. Reuse the `_CACHE` pattern keyed by original bullet text, redacted job, requirement, keyword, goal, `PROMPT_VERSION` and model. Bump `PROMPT_VERSION`, or give this module its own version constant so review caching isn't disturbed.

### Fine as written

- Saving nothing on the suggest call.
- Model choice behind `OPENROUTER_MODEL` and `is_free_model`.
- Marker on the library variant row only. `render.py` and the PDF read `wording_snapshot`, so nothing new leaks into output as long as the marker isn't put into `render_payload`.
- The revision check on Accept (it comes free with `_lock_composition`).

## Part 2. Blueprint

### Data: `backend/migrations/024_bullet_variant_ai_provenance.sql`

```sql
-- AI provenance on bullet wording. ai_generated means the body is still the
-- model's text unchanged. Model and job stay as history after an edit.
ALTER TABLE bullet_variants
  ADD COLUMN ai_generated boolean NOT NULL DEFAULT false,
  ADD COLUMN ai_model text,
  ADD COLUMN ai_job_id uuid REFERENCES job_descriptions (id) ON DELETE SET NULL;

CREATE OR REPLACE FUNCTION clear_ai_generated_on_body_change () RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.body IS DISTINCT FROM OLD.body AND NEW.ai_generated IS NOT DISTINCT FROM OLD.ai_generated THEN
    NEW.ai_generated := false;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER bullet_variants_clear_ai_generated
BEFORE UPDATE OF body ON bullet_variants
FOR EACH ROW EXECUTE FUNCTION clear_ai_generated_on_body_change ();
```

The condition lets a writer set the flag on purpose in the same statement; a plain body edit clears it.

### Backend

**B1. Placement id in match data**

- `job_repository._placed_bullets`: select `cb.id::text AS placement_id`, add `cb.id` to the `GROUP BY`, return it.
- `job_match._bullet_candidates`: carry `placement_id`.
- `_placement_options` and `_skills_fallback`: include `placement_id` (empty for skills).
- `job_schemas.TagSuggestion`: `placement_id: str = ""`.
- Check where else `_placed_bullets` feeds the matcher (`_compare_job`) so both deterministic match and AI review get it.

**B2. `backend/app/ai_variants.py`**

```python
VARIANT_PROMPT_VERSION = "1"
Goal = Literal["concise", "impact", "align"]  # or drop for v1
GUARDED_CATEGORIES = {"tool", "credential", "degree", "experience_duration"}

class VariantDraft(BaseModel):
    name: str          # <= 60, used as variant name
    body: str          # <= 500
    rationale: str     # <= 240

class VariantSuggestions(BaseModel):
    status: Literal["ok", "unavailable", "rate_limited", "invalid"]
    detail: str = ""
    model: str = ""
    drafts: list[VariantDraft] = []
    dropped: int = 0   # count only, never the text

async def suggest_variants(original, job_text, requirement, keyword, category, goal,
                           *, complete=complete_json) -> VariantSuggestions
```

Flow:

1. Gate: same empty-key and `is_free_model` checks as `review_resume`; return `unavailable` without a network call.
2. Input: `redact_job(job_text)` truncated to 12,000 chars; original bullet with emails, URLs and phones stripped (reuse the redaction helpers); requirement and keyword; goal.
3. System prompt: rewrite only the given bullet; facts must come from the bullet (keyword mode, added later: every draft must also use the keyword, or the model says it doesn't fit; see `docs/keyword_incorporation_plan.md`); the job may guide emphasis and word choice; for guarded categories never add the keyword; return `{"drafts":[{name, body, rationale}]}`, 3 to 5 items, each a distinct angle.
4. Call `complete(...)` with the `complete=` injection hook, as `ai_review` does, so tests never hit OpenRouter.
5. Filter (see B3), dedupe, cap 5. Zero survivors gives `status: "ok"` and an empty list; the dialog then offers Write my own.
6. Cache on success. Log counts and latency to `resume_engine.ai`, never text.

**B3. Guardrail filter (`filter_drafts`)**

A draft is dropped when any of these holds:

- **Numbers:** any token matching `\d[\d,.]*%?|\$\d…` (and spelled numbers `one`…`twenty`, `dozens`, `hundreds`) not present in the original after normalization.
- **Tools:** any term from the related-skills dictionary (`related_skills.yaml`) or the job's extracted tool keywords that appears in the draft but not in the original. This is the check that stops job keywords turning into claimed experience.
- **Proper nouns:** capitalized tokens not at sentence start, plus all-caps acronyms of 2+ letters, that don't appear in the original. Allow a short list of common verbs and words that are often capitalized.
- **Guarded keyword:** category is in `GUARDED_CATEGORIES` and the keyword appears in the draft but not in the original.
- Body is empty, over 500 chars, or more than about 1.6× the original length.
- Body equals the original or an earlier draft after case and whitespace folding.

Keep it a pure function with unit tests. It's the part most likely to need tuning.

**B4. Endpoints in `main.py`**, next to the existing `bullet-placements/{placement_id}` routes:

```
POST /api/compositions/{cid}/bullet-placements/{placement_id}/ai-variants
  body: { job_id, revision, keyword, requirement, goal? }
  -> VariantSuggestions        (saves nothing)

POST /api/compositions/{cid}/bullet-placements/{placement_id}/ai-variants/accept
  body: { revision, name, body, source: "draft"|"edited"|"own", job_id?, model? }
  -> CompositionState          (409 on stale revision, 404 on missing)
```

The suggest route loads the placement's current `wording_snapshot` on the server. It never trusts bullet text sent from the client. It also loads the job by `job_id` for this user (404 if missing). It reads keyword category from the job's `keyword_review` or the AI review cache when available, and falls back to the matcher row's `kind`.

The accept route calls `save_bullet_edit(conn, uid, cid, placement_id, revision, body, "variant", name=name, ai=...)` where `ai` is:

- `source == "draft"`: `ai_generated=true`, `ai_model`, `ai_job_id`
- `source == "edited"`: `ai_generated=false`, `ai_model`, `ai_job_id`
- `source == "own"`: nothing

The client sends `model` back, but it's only a label. To keep it honest, have the suggest response include a short HMAC token over `(placement_id, body, model, job_id)` and set `ai_generated=true` only if the token verifies and the body is unchanged. Without that, a client could mark any text as AI-written, which matters little for a single-user app. Skip the token if you don't care.

**B5. Repository changes**

- `resume_variants.save_bullet_edit`: optional `name` (passed through `_unique_name`, truncated to 120) and an optional `ai` dict written in the same `INSERT`. The existing default of `"Variant"` stays for normal saves.
- `editing_repository.duplicate_variant`: copy the three provenance columns.
- Variant list queries used by the library (`library_repository` / `library_schemas`): return `ai_generated`, `ai_model`, `ai_job_id`, and the job's company and role via a left join for the tooltip.

**B6. Schemas**: `AiVariantRequest`, `AiVariantAccept` (both `extra="forbid"`, `revision: int = Field(ge=1)`), plus `VariantSuggestions` in `ai_schemas.py`.

### Frontend

**F1. Preview button (`backend/app/templates/resume.html` and `ResumePreview.tsx`)**

The preview is an iframe rendered by the backend template, so the button lives in the iframe script, next to `highlightLines`:

- When marks arrive, for each `li[data-bullet-id]` that got a `suggestion` mark, set `data-suggest="true"`.
- On `mouseover` / `focusin` (and first tap on touch) of such a line, show one absolutely positioned `<button class="suggest-chip">Suggest</button>` at the line's top-right. Reuse a single element. Make lines with `data-suggest` focusable (`tabindex="0"`) only in highlight mode.
- On click: `parent.postMessage({ type: "resume-suggest", lineId, matchIds }, "*")`.
- `@media print { .suggest-chip { display: none } }`, and only inject it in the `{% if %}` highlight block that already guards the hover code, so PDF output can never include it.
- `ResumePreview.tsx` already checks `e.source === frame.current.contentWindow`. Add an `onSuggest(lineId, matchIds)` prop next to `onHighlightHover`.

**F2. `SuggestVariantDialog.tsx`** (new, built on `ModalShell`)

Props: `compositionId`, `revision`, `placementId`, `original`, `job` (`CompareJob`), `keyword`, `requirement`, `onApplied(state)`.

Layout, top to bottom:

1. Header: "Suggest wording", then `job.title · job.company`.
2. Original bullet, read-only, muted.
3. Goal segmented control (if kept): Concise / Impact / Match the requirement. Changing it refetches.
4. Guard note when the keyword is a guarded category (Part 1, item 6). For a tool keyword it also shows an **Add to Skills instead** link, which opens `AddSkillDialog`.
5. Options as a radio group (`role="radiogroup"`); each card is a radio:
   - Draft cards: name, body, rationale in smaller text, and an **Edit** button that turns the body into a textarea in place (the source becomes `edited` once the text differs).
   - **Write my own**: textarea pre-filled with the original.
6. Footer: **Close** (no change) and **Use this wording** (disabled until something is selected and its text is non-empty and different from the original).

States:

- Loading: skeleton cards, with the same "Reviewing…" wording `JobMatchPanel` uses.
- `unavailable` / `rate_limited` / `invalid`: reuse the panel's status copy, extracted into a shared `aiStatusMessage(status)` helper so the wording can't drift. Write my own stays usable.
- 409 on accept: "This resume changed. Reload to see the latest, then try again." Keep the dialog open with the user's text.
- Zero drafts after filtering: "No safe rewrites. The model's ideas added facts the bullet doesn't show." Write my own stays open.

Phone width: full-screen sheet, cards stacked, footer sticky, no horizontal scroll at 375px.

**F3. Wiring in `App.tsx`**

- Keep `lineId → { placementId, keyword, requirement, excerpt }` from the current match response; `buildMatchMarks` gets the rows, so add a parallel `buildSuggestTargets(rows)` in `matchMarks.ts`.
- On `onSuggest`, look up the target. If there's no `placementId` (skill line), do nothing. Open the dialog with `compareJob`.
- `onApplied`: replace `comp` with the returned state (revision bumps, preview refetches), then re-run the match so the mark updates.

**F4. Library marker (`StandaloneLibrary.tsx`, variant cards around line 1166)**

A small "AI-written" badge in `variant-card-header` when `ai_generated`. Tooltip: "Drafted by {model} for {role} at {company}". When `ai_generated` is false but `ai_model` is set, show nothing, or a subtle "AI-assisted". Never pass it to the preview.

**F5. Existing review suggestions**: in `AiReviewBody`, add "Open in Suggest" on a rewrite card when its `resume_quote` matches a placed bullet's excerpt (Part 1, item 12).

### Skills quick add

**Purpose.** A missing tool can be added to the resume's Skills section in two clicks, and the user picks the group. Groups are the user's own `tool_groups` rows (today Languages / Platforms / Collaboration Tools), so nothing may assume those names. The app recommends a group using local data first. It asks the model only when local data has no answer, and it never adds anything without the user confirming.

**What the code does today**

- `tools.group_id → tool_groups`, both library-wide with `UNIQUE (group_id, name)`. A resume includes a group through `composition_items(section='tool_groups')` and hides single tools through `composition_hidden_tools`.
- `create_tool` (`library_repository.py:828`) calls `_refresh_tool_compositions`, which re-renders **every** resume that includes the group. A plain add would change other resumes, which goes against this plan's rule that other resumes are unaffected. It also isn't revision-locked.
- The matcher already ranks skill groups against a keyword (`_placement_options` over the `skill_group` candidates, using `related_mention` / `combination_mention`). Those candidates are keyed `tool-group-{index}` and carry no group id.

**S1. Recommendation ladder** (`backend/app/skill_groups.py`, new, pure functions plus one DB loader)

```python
@dataclass
class GroupOption:
    group_id: str; name: str; on_resume: bool
    score: float; reason: str

@dataclass
class SkillRecommendation:
    label: str                      # normalized display label, e.g. "Node.js"
    existing: ExistingTool | None   # tool_id, group_id, state
    groups: list[GroupOption]       # every active group, best first
    recommended_group_id: str | None
    new_group_name: str | None      # only when no group fits
    source: Literal["library", "related", "hint", "ai", "none"]
```

The steps run in order and stop at the first confident answer:

| Step | Source | Rule | Example reason shown |
|---|---|---|---|
| 0 | Normalize | Display label from the dictionary (`_display_label`, aliases), so "nodejs", "Node JS" and "Node.js" are one term. | — |
| 1 | `library` | The tool already exists in any group, including archived ones, compared by normalized name. Recommend that group and report its state (see S3). | "Already in your Platforms group." |
| 2 | `related` | For each active group, score its existing tool names with the matcher's evidence (`related_mention`, `combination_mention`, shared clusters from `clusters_in_text`). Highest score wins if ≥ 1 strong link. | "Platforms already lists Docker, which is related to Kubernetes." |
| 3 | `hint` | Map the keyword's cluster and category to hint words, and match them against group-name tokens. | "Matches the group name Languages." |
| 4 | `ai` | Only if steps 1–3 give nothing **and** the free-model gate passes. A separate request, so the dialog never waits on it. | "Suggested by AI." |
| 5 | `none` | No preselection. All groups are listed, plus New group. | — |

Step 3 data lives in `related_skills.yaml`, so it can be edited without touching code and works for any group names:

```yaml
group_hints:
  # hint word sets, matched against tokens of the user's group names
  language: [language, languages, programming, coding, scripting]
  platform: [platform, platforms, cloud, infrastructure, devops, systems]
  data: [data, analytics, bi, reporting, database, databases]
  collaboration: [collaboration, communication, productivity, project, teamwork]
  design: [design, creative, media]
cluster_hints:
  python: language
  java: language
  javascript: language
  cloud: platform
  observability: platform
  bi: data
  sql: data
  nosql: data
  # clusters without an entry fall back to their category below
category_hints:
  tool: [platform, data]
```

`RelatedSkills` loads the new sections. `test_related_skills_dictionary.py` checks that every `cluster_hints` key is a real cluster and every value is a real hint set.

If no group exists, or the best group scores below the threshold and the hint step points at a hint set no group matches, set `new_group_name` from that hint set's title, for example "Data".

**S2. AI fallback** (in `skill_groups.py`, using `complete_json` with the `complete=` hook)

- Input: the keyword, plus the list of `{id, name, tools[:10]}` for active groups. No resume text, contact data, or job text is sent; group and tool names are enough.
- Output: `{"group_id": "<one of the ids>" | null, "new_group_name": str | null, "rationale": str}`.
- Validation: drop a `group_id` that isn't in the list, a `new_group_name` over 60 characters, or one equal to an existing group name compared case-insensitively. If both survive, keep the existing group.
- Cache key: normalized keyword, sorted group names and tool names, prompt version, and model. Errors use the same `unavailable` / `rate_limited` / `invalid` statuses. The dialog keeps working without a recommendation.

**S3. Endpoints** (`main.py`, next to the composition tool routes)

```
POST /api/compositions/{cid}/skills/recommend
  body: { keyword, allow_ai: false }
  -> SkillRecommendation           (reads only)

POST /api/compositions/{cid}/skills
  body: { revision, name, group_id? , new_group_name? }
  -> CompositionState              (409 stale, 404 missing group, 422 if neither group field)
```

The frontend calls `recommend` with `allow_ai=false` first. If `source == "none"`, it calls again with `allow_ai=true` in the background.

`add_skill_to_resume` (new, in `library_repository.py`) runs in **one transaction**:

1. Lock the target composition at `revision` (same pattern as `set_tool_visibility`).
2. Find or create the group. A new group gets the next `sort_order`, and its name goes through a unique-name helper.
3. Look for the tool by normalized name across the user's tools. Then:
   - **active in that group:** reuse it.
   - **active in another group:** if the user kept that group (step 1 preselects it), reuse the tool. If they picked a different group, insert a new row in the chosen group (`UNIQUE (group_id, name)` allows this). Never move the existing row, because a move changes other resumes.
   - **archived:** restore it into the chosen group. Restoring makes it visible again everywhere that includes the group, so step 6 applies to it as well.
   - **missing:** insert it.
4. If the group isn't on this resume, add the `composition_items` row, and insert `composition_hidden_tools` rows for the group's **other** tools on this resume. The user asked for one skill, so the rest of the group shouldn't appear with it. They can show those tools later with the existing per-tool toggle.
5. Delete any `composition_hidden_tools` row for this resume and tool.
6. For every **other** composition that includes the group and didn't already show this tool (a new or restored row), insert a `composition_hidden_tools` row. This always happens; there is no option. The skill goes into the library and onto this resume only.
7. Re-render **only** the target composition (revision bump and history row). Other compositions keep their `render_payload`, revision and history untouched. Their output doesn't change, because the hidden rows from step 6 match what they already render.

Don't call `create_tool` from here, since it re-renders every resume that includes the group. Share the insert SQL with it instead.

**S4. Match data**

- `skill_group` candidates in `job_match.py` get `group_id` (the render payload's group id, or load it beside the groups) and keep `line_id`.
- `TagSuggestion` gets `group_id: str = ""` and `action: Literal["add_skill", "rewrite", ""] = ""`. Set `add_skill` on the `tools` fallback, on `tool-group-*` options, and on any option whose keyword is a dictionary `tool`. Set `rewrite` on bullet options for non-tool keywords. The frontend branches on `action`, so the rule lives in one place.

**S5. UI**

- **Where the button appears**
  - In `JobMatchPanel`, on every unfound keyword row whose suggestions include `action == "add_skill"`: an **Add to Skills** button next to the keyword.
  - In the preview, a suggestion line with an `add_skill` mark (the Skills line or a group row) gets the same chip as F1, labeled **Add to Skills**, posting `{ type: "resume-add-skill", keyword }`.
  - The Suggest dialog shows the link from F2 for tool keywords.
- **`AddSkillDialog.tsx`** (new, on `ModalShell`)
  1. Name field, pre-filled with the normalized label and editable.
  2. Note: "Only add skills you've used."
  3. Groups as a radio list, built from the recommendation response and never hardcoded. The recommended group is first and preselected, and the reason line sits under it. Groups not on this resume carry a "Not on this resume yet" tag; choosing one adds the group too.
  4. **New group** option with a name field, pre-filled with `new_group_name` when set.
  5. Existing-tool states replace the default copy: "Already in Platforms. Show it on this resume." / "Restore from archive into Platforms." / "In Languages on your other resumes."
  6. While the AI fallback runs, show "Looking for a group…" under the list. Nothing is preselected until it returns, and its errors are silent apart from "No suggestion."
  7. A footnote under the list: "Adds to your Library and this resume. Other resumes aren't changed."
  8. Buttons: **Cancel** and **Add**. On 409, show the same reload message as Suggest.
- **After adding**: replace `comp` with the returned state, reload the library, and re-run the match. The keyword should now be found.
- **Phone width**: same sheet layout as the Suggest dialog.

### Tests

| File | Covers |
|---|---|
| `tests/test_ai_variants.py` (new, unit, `complete=` injected) | Drafts parsed from fenced and unfenced JSON; extra fields ignored; >5 capped; new number / tool / proper noun / guarded keyword each dropped; job keyword allowed for soft categories; dedupe against original and siblings; empty-key and paid-model give `unavailable` with no call; each `AiCallError` status mapped; cache hit skips the call |
| `tests/test_ai_variants_integration.py` (new, DB) | Accept creates variant + swaps placement + bumps revision in one transaction; stale revision gives 409 **and no new variant row**; name collision gets a suffix; other compositions using the same bullet keep their snapshot; `draft` / `edited` / `own` provenance values; `update_variant` body change clears flag, rename keeps it; overwrite-mode save clears flag; duplicate copies flag; deleting the job nulls `ai_job_id`; suggest on another user's placement or job gives 404 |
| `tests/test_job_match.py` (extend) | `TagSuggestion.placement_id` set for bullet lines, empty for `tools`; `action` is `add_skill` for tool keywords and skill lines, `rewrite` for non-tool bullet options; `group_id` set on skill-group options |
| `tests/test_skill_groups.py` (new, unit) | Groups named arbitrarily (`"Stack"`, `"Cloud stuff"`, `"Misc"`) to prove nothing depends on today's names; library precedent wins over related; related ("Docker" in a group recommends it for "Kubernetes"); hint step matches "Programming Languages" for a Python-cluster term; alias dedupe ("nodejs" finds "Node.js"); no groups gives `new_group_name`; **the AI hook is not called when any local step answers**; AI `group_id` not in the list is dropped; AI name equal to an existing group is dropped; AI errors keep `source: "none"` |
| `tests/test_skill_quick_add_integration.py` (new, DB) | Adds the tool to the library and this resume, includes the group, unhides it; other resumes that include the group get a hidden row and keep the same revision, `render_payload` and history count; restoring an archived tool also hides it on other resumes; a group newly added to this resume shows only the added tool; stale revision gives 409 **and no tool or group row**; archived tool is restored, not duplicated; tool active in another group is reused and not moved; new group name collision gets a suffix; another user's group gives 404 |
| `tests/test_related_skills_dictionary.py` (extend) | `cluster_hints` keys are clusters and values are hint sets |
| Failure statuses | For each of unavailable, rate_limited, invalid: suggest returns the status and the composition revision and placement are unchanged |
| `tests/resume-layout.spec.ts` (extend) | Both dialogs at 375×812: no horizontal overflow, footer visible, cards stacked; Suggest chip appears on a rewrite line and not on match-only lines; a tool keyword shows Add to Skills and no Suggest chip; chips hidden under print media |
| Contract test (pattern of `test_phase*_contract.py`) | `suggest-chip` only inside the highlight block of `resume.html`; `ai_generated` not present in `render_payload` or `render.py` |

### Build order

1. Migration 024, trigger, duplicate fix, and the integration tests for provenance. Nothing user-visible yet.
2. `placement_id`, `group_id` and `action` through the match data (B1, S4) and their tests.
3. **Skills quick add, local only:** `group_hints` in the dictionary, `skill_groups.py` steps 0–3, `add_skill_to_resume`, both endpoints, `AddSkillDialog`, and the panel button. This ships on its own and needs no model, so it's the cheapest win and covers most missing keywords.
4. AI group fallback (S2).
5. `ai_variants.py` with the filter and unit tests.
6. Suggest endpoints and the `save_bullet_edit` extension, with integration tests.
7. Suggest dialog component on its own, against a stubbed API.
8. Iframe chips (Suggest and Add to Skills) and App wiring, then the layout spec.
9. Library badge; review "Open in Suggest" link.
10. Update `ai_overview.md` with the new modules, endpoints, invariants and cache keys.

### New invariants to add to `ai_overview.md`

- Suggestions never change the match score; the next deterministic match decides.
- No draft is saved without an explicit Accept.
- A draft may not add a number, tool, proper noun, or guarded-category keyword absent from the original bullet.
- The server reads the bullet text from the placement, never from the client.
- `ai_generated` is true only for unchanged model text, and is never rendered into a resume or PDF.
- Missing tools are offered as Add to Skills, never as an AI rewrite.
- Skill group choice uses library, dictionary and hint data first. The model is called only when all of those give nothing, sees only group and tool names, and can only pick a listed group or propose a new name.
- Skill group names are never hardcoded; the list is always the user's `tool_groups`.
- Adding a skill from a resume writes to the library and that resume only. Other resumes' payload, revision and history are never touched.
