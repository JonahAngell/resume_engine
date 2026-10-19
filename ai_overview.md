# AI review (current build)

This is the source of truth for the optional AI review. Calls go to the Studioshare AI Gateway first when it is configured, then to free OpenRouter models. Older design notes in `docs/resume_engine_related_skills_review/IMPLEMENTATION_NOTES.md` describe recommendations. Where they disagree with this file, follow the code listed below.

The match score is deterministic. AI never changes `required_matched`, `preferred_matched`, score components, or eligibility. A semantic candidate becomes a match only after the user clicks **Mark as a match**, which writes `keyword_review.matched` through the existing job-save path.

## Files

| Path | Role |
|---|---|
| `backend/app/ai_client.py` | Provider chain (Studioshare AI Gateway, then OpenRouter free models). Gateway OIDC token, JSON parse, one rate-limit retry, one JSON repair per model. |
| `backend/app/ai_review.py` | Redaction, prompts, filtering, in-memory cache, `review_resume`. |
| `backend/app/ai_schemas.py` | `AiReview` and nested Pydantic models. |
| `backend/app/job_match.py` | Deterministic matcher. `match_qualifications` always runs first. `analyze_requirements` supplies extra rows the AI may label. |
| `backend/app/job_repository.py` | `load_ai_review_inputs`, `link_job_composition`. |
| `backend/app/job_schemas.py` | `JobMatch`, `JobMatchRequest`, `KeywordReview`. |
| `backend/app/main.py` | `POST /api/job-descriptions/{job_id}/ai-review`. |
| `frontend/src/match/` | Job match dashboard (the old `JobMatchPanel.tsx` and its Review with AI button are removed). |
| `tests/test_ai_review.py` | Redaction, grounding, cache, partial failure, client retries, paid-model and missing-key refusal. |
| `tests/test_ai_providers.py` | Provider order, gateway fallback on 401/403/5xx, model list, OIDC token minting and caching. |
| `tests/conftest.py` | Clears `STUDIOSHARE_*` gateway vars so a developer shell cannot leak into tests. |
| `docker-compose.yml` | Passes `OPENROUTER_*` and the `STUDIOSHARE_*` gateway variables. |
| `GET /api/ai/status` | Lists the configured providers and models. No secrets. |
| `test_openrouter_key.py` | Manual key check. Not part of the app. |

## Request path

1. Job match panel calls `POST /api/job-descriptions/{job_id}/ai-review` with `{ "composition_id": "<uuid>" }`.
2. `load_ai_review_inputs` loads the job `body`, the composition `render_payload`, placed bullets, `keyword_review`, and `revision`. Missing job or resume is HTTP 404.
3. `review_resume` calls `match_qualifications` and keeps that result on `AiReview.match`.
4. If no provider is configured (`ai_available()` is false), return `status: "unavailable"` and do not call the network.
5. Redact the job and resume. On a cache hit, return the cached payload with the current `composition_id`.
6. Run up to two calls in parallel: `job_review` and, when there are unmatched requirements or bullets, `resume_comparison`.
7. Filter both payloads. If every call failed, return that error status with the deterministic match. If at least one call succeeded, return `status: "ok"` and keep only the successful side.
8. Cache a successful review. Then `link_job_composition` stores this resume id on the job. The AI payload itself is not stored.

## Providers

`providers()` in `ai_client.py` builds the chain on every call:

1. **Studioshare AI Gateway**, when `STUDIOSHARE_AI_GATEWAY_URL` is set and either `STUDIOSHARE_OIDC_TOKEN` or `STUDIOSHARE_OIDC_URL` is set. Posts to `${STUDIOSHARE_AI_GATEWAY_URL}/v1/chat/completions`. Each model in `STUDIOSHARE_AI_MODELS` is tried in order.
2. **OpenRouter**, when `OPENROUTER_API_KEY` is set and `OPENROUTER_MODEL` is free.

`complete_json` moves to the next model or provider when a call ends in `unavailable`, `rate_limited`, or `invalid`. A 401 from the gateway clears the cached token and skips the rest of the gateway models. If every attempt fails, the last status is raised.

The gateway token is app-scoped. `STUDIOSHARE_OIDC_TOKEN` (from `launch env pull`, 12 hours) wins. Otherwise the server POSTs to `STUDIOSHARE_OIDC_URL` (the Launch sidecar) and keeps the token until 5 minutes before `expiresAt`. A failed mint skips the gateway for that call. The user's `access_token` cookie is not sent to the gateway.

The app needs **Use** permission on the gateway provider that serves each listed model (AI console).

`model_name()` returns a label for the whole chain, such as `studioshare:anthropic/claude-sonnet-4-6|openrouter:openrouter/free`. Callers put it in cache keys, so changing providers or models invalidates the caches. `AiReview.model` still stores the served model id.

## Environment

| Variable | Behavior |
|---|---|
| `STUDIOSHARE_AI_GATEWAY_URL` | Injected by Launch. Enables the gateway when a token source is also set. |
| `STUDIOSHARE_OIDC_URL` | Injected by Launch in production. POSTed to mint a short-lived token. |
| `STUDIOSHARE_OIDC_TOKEN` | Local dev, from `launch env pull`. Re-run it when the token expires; until then the gateway returns 401 and calls fall back to OpenRouter. |
| `STUDIOSHARE_AI_MODELS` | Optional comma-separated gateway model ids. Default `anthropic/claude-sonnet-4-6`. |
| `OPENROUTER_API_KEY` | Enables OpenRouter. Empty skips it. |
| `OPENROUTER_MODEL` | Default `openrouter/free`. Allowed: that id, or any id ending in `:free`. Anything else skips OpenRouter. |
| `OPENROUTER_APP_URL` | Optional `HTTP-Referer` header. |

OpenRouter endpoint: `https://openrouter.ai/api/v1/chat/completions`. Temperature is `0`. Timeout is 30 seconds. `PROMPT_VERSION` in `ai_client.py` is `"1"`. Bump it when prompt or schema meaning changes so the cache key changes.

`JOB_SCHEMA` and `COMPARE_SCHEMA` are defined in `ai_review.py`, but `complete_json` always posts with `use_schema=False`. The model is asked for JSON in the system prompt. Do not assume `response_format` is sent unless that flag is turned on.

## Client outcomes

`complete_json` returns `AiCompletion(data, model)` or raises `AiCallError` with one of `unavailable`, `rate_limited`, `invalid`.

- HTTP 429: sleep `Retry-After` (capped at 5 seconds) and retry once. A second 429 is `rate_limited`.
- HTTP 400 or 422: `schema_rejected`, then the JSON repair path. A still-unusable body becomes `invalid`.
- HTTP 401: the gateway token is rejected; move to the next provider.
- Other HTTP errors (including 403), timeouts, and transport errors: `unavailable` with no repair call; move to the next model.

These outcomes apply per model. The chain then decides what to try next (see Providers).
- A 200 whose content is not one JSON object: append `"Return one JSON object only, with no markdown."` and call once more. Still unusable: `invalid`.
- Markdown fences are stripped. The first `{` through the last `}` is parsed.
- If the served model name contains `content-safety`, `moderation`, or `guard`, the body is discarded.
- The served model id from the response is what gets stored on `AiReview.model`, not only the requested id.

Logs use the `resume_engine.ai` logger: provider, model, prompt version, latency, outcome, token counts, and validation keep/drop counts. Do not log raw resume or job text.

## What the model receives

`redact_resume` builds a new object. It does not send the full resume.

Kept: `summary`, skill and tool-group names (max 80), degree strings, role titles from work, leadership, and projects, and bullets (max 40, minimum 8 characters). Bullet sources are placed composition bullets first, then work, projects, leadership, skill-group bullets, and education bullets.

Removed before send: header name, phone, email, LinkedIn label and URL, and location fields, including comma-separated parts of those values. Emails, URLs, and phone numbers are stripped from every remaining string. Employer names are omitted because they are not copied into the redacted shape. They are not a separate secret list.

`redact_job` only strips emails, URLs, and phone numbers. The posting sent to the model is truncated to 12,000 characters. The user message also includes up to 40 requirement rows from the matcher.

## Prompts

`job_review` system prompt asks for `families`, `requirements`, and `keywords`. Categories are `tool`, `domain`, `responsibility`, `methodology`, `credential`, `degree`, `experience_duration`, `soft_skill`. Each requirement and keyword needs an exact `source_span` from the posting. Pay, benefits, and legal boilerplate are out of scope.

`resume_comparison` system prompt asks for `semantic_candidates`, `bullet_tags`, and `suggestions`. A semantic `resume_span` and a suggestion `resume_quote` must be exact quotes. Suggestions may only rephrase quoted resume text. Bullet tags are `action`, `domain`, `skill`, `tool`, `outcome`, `metric`, and empty tags are allowed in the prompt but dropped if every tag is empty.

## Filter rules

Unknown or extra JSON fields are ignored. Items that fail a rule are dropped and counted. They do not fail the whole review.

Job families: non-empty label, at most 80 characters, confidence at least `0.4`, unique. Cap 6. Values from 1 to 100 are treated as percents.

Requirements: category must be known. `source_span` must appear in the job text. If the text matches one matcher row, keep that row's text and group, and the span must overlap that text. Otherwise the model text must sit inside the span, and `group` must be `required`, `preferred`, or `responsibilities` (`responsibility` is aliased). Cap 40.

Keywords: category known, keyword appears inside `source_span`, span appears in the job text. Cap 30.

Semantic candidates: requirement matches exactly one unmatched row, confidence at least `0.55`, `resume_span` appears in the redacted resume. One per requirement. Section is kept only when it matches a bullet section. Rationale capped at 400 characters. Cap 20.

Bullet tags: `bullet` must equal a redacted bullet after whitespace and case folding. At least one tag field must be non-empty. Cap 40.

Suggestions: `resume_quote` must appear in the redacted resume, suggestion non-empty (capped at 500), requirement must match an unmatched row. Cap 12.

`span_in` compares compact, case-insensitive substrings. Quotes shorter than 2 characters fail.

## Response

`AiReview`: `composition_id`, `status` (`ok`, `unavailable`, `rate_limited`, `invalid`), `detail`, `model`, `match` (`JobMatch`), `families`, `requirements`, `keywords`, `semantic_candidates`, `bullet_tags`, `suggestions`.

`detail` for the three error statuses says the match score is unchanged. The panel shows that message when status is not `ok`. An `ok` review with every list empty shows: "The model did not add anything beyond the current match."

Partial success is `ok`. Example: job call succeeds and comparison is rate limited. Categories are kept. Semantic candidates, tags, and suggestions stay empty. The score is still the deterministic score.

## Cache

Module dict `_CACHE`, max 32, insertion order. Key is a SHA-256 of redacted job, redacted resume, composition `revision`, `keyword_review`, `PROMPT_VERSION`, model name, and a 16-character hash of the related-skills dictionary file. Cleared only by process restart or `clear_cache()` in tests. Not shared across workers.

## UI

The review endpoint is no longer called from the UI; the Job match dashboard uses the AI coach instead (see the dashboard section below). **Mark as a match** still goes through `markRequirement`, which toggles that requirement text in `keyword_review.matched` and saves the job. AI does not set `matched` itself.

## Invariants for later changes

- Keep `match_qualifications` as the only scorer. Do not add AI evidence into coverage or eligibility.
- Do not send contact fields, and do not log prompt bodies.
- Do not call a paid model. `is_free_model` is the gate.
- Do not keep a model claim whose quote is not in the source text.
- Do not auto-apply suggestions or semantic matches.
- Tests in `tests/test_ai_review.py` inject `complete=` so they do not hit OpenRouter. Preserve that hook.
- `test_openrouter_key.py` is a manual script. Do not import it from the app.
# AI bullet suggestions and Skills quick add

Design notes and the review behind these features are in `docs/ai_suggestions_blueprint.md`. This section describes what the code does.

## Files

| Path | Role |
|---|---|
| `backend/app/ai_variants.py` | Prompt, guardrail filter (`drop_reason`, `filter_drafts`), cache, issued-draft record, `suggest_variants`. |
| `backend/app/ai_keyword.py` | Work into resume: one keyword across the whole resume (`assist_keyword`, `filter_keyword`, `resume_entries`). |
| `backend/app/skill_groups.py` | Local group ladder (`recommend_group`), AI fallback (`recommend_with_ai`), `same_skill`. |
| `backend/app/related_skills.yaml` | `group_hints`, `cluster_hints`, `category_hints` for the hint step. |
| `backend/app/library_repository.py` | `load_skill_inputs`, `add_skill_to_resume`. |
| `backend/app/job_repository.py` | `load_variant_inputs` (placement wording and job text). |
| `backend/app/resume_variants.py` | `save_bullet_edit(..., name=, ai=)` writes the accepted variant. |
| `backend/migrations/024_bullet_variant_ai_provenance.sql` | `ai_generated`, `ai_model`, `ai_job_id` and the body-change trigger. |
| `frontend/src/SuggestVariantDialog.tsx`, `frontend/src/AddSkillDialog.tsx`, `frontend/src/KeywordAssistDialog.tsx` | The dialogs, opened from the dashboard and the highlight popover (state in `App.tsx`). `KeywordText.tsx` marks the keyword and `[placeholders]` in drafts. |
| `backend/app/templates/resume.html` | Preview chip (Suggest / Add to Skills), inside `{% if measure %}` only. |
| `tests/test_ai_variants*.py`, `tests/test_skill_*.py`, `tests/test_ai_suggestions_contract.py` | Unit, database and contract tests. |

## Endpoints

| Route | Saves | Notes |
|---|---|---|
| `POST /api/compositions/{cid}/bullet-placements/{pid}/ai-variants` | nothing | Body: `job_id`, `keyword`, `requirement`, `category`, `goal` (`concise`/`impact`/`align`), `incorporate_keyword`. Bullet text is read from the placement. In keyword mode every draft must contain the keyword (or a dictionary form of it), and the reply carries `fits`/`reason` when the model says it doesn't fit. |
| `POST /api/compositions/{cid}/ai-keyword-assist` | nothing | Body: `job_id`, `keyword`, `requirement`, `category`. Returns up to 3 `revisions` (one per placed bullet), up to 2 `new_bullets` (each tied to a role or project), the `entries` a new bullet can go under, `allowed`, `no_fit_reason`. Guarded keywords return `allowed: false` without calling the model. |
| `POST /api/compositions/{cid}/ai-keyword-assist/accept-new` | bullet + variant + placement | Body: `revision`, `parent_id` (a role or project on this resume), `body`, `source`, `job_id`, `model`. 422 while the body still has a `[placeholder]`; 404 for an entry not on this resume; 409 on a stale revision. Revisions are accepted through `.../ai-variants/accept`. |
| `POST /api/compositions/{cid}/bullet-placements/{pid}/ai-variants/accept` | variant + placement | Body: `revision`, `name`, `body`, `source` (`draft`/`edited`/`own`), `job_id`, `model`. 409 on a stale revision, with no variant written. |
| `POST /api/compositions/{cid}/skills/recommend` | nothing | Body: `keyword`, `allow_ai`. The UI calls with `allow_ai=false` first and again with `true` only when `source == "none"`. |
| `POST /api/compositions/{cid}/skills` | tool, group, this resume | Body: `revision`, `name`, and `group_id` or `new_group_name`. |

## Match data

Each `RequirementKeyword` carries `skill` (`is_skill_keyword`): skill keywords get Add to Skills, every other missing keyword gets Work into resume. `TagSuggestion` carries `placement_id` (bullet lines) and `action`: `add_skill` for dictionary tools, unknown terms on tool rows, `tool-group-*` lines and the `tools` fallback; `rewrite` for other keywords on a placed bullet. `matchMarks.ts` turns these into `targets` so the preview chip can find a line by id, or by its text when the id is not in the preview.

## Provenance

`ai_generated` is true only when `source == "draft"` and the body exactly matches a draft this process issued for that placement and job (`issued_draft`). New bullets from Work into resume are issued under `new:{parent_id}`, so moving one to a different entry, or filling in a placeholder, counts as an edit. An edited draft stores `ai_model` and `ai_job_id` with `ai_generated = false`. Write my own stores none. Any later body change clears `ai_generated` through the trigger; renames keep it. Duplicating a variant or a bullet copies all three columns. Deleting the job nulls `ai_job_id`. The library shows an "AI-written" badge; nothing is rendered into the resume or PDF.

## Guardrails

A draft is dropped when it adds a number (digits or spelled), a dictionary term or capitalised job keyword that the original does not show, a mid-sentence capitalised word or acronym not in the original, or, for `tool`/`credential`/`degree`/`experience_duration`, the keyword itself. Domain, methodology, responsibility and soft-skill keywords may appear. In keyword mode a draft without the keyword is dropped (`missing_keyword`). A new bullet is checked the same way with its entry (title, organization, location and that entry's bullets) as the original, without the length-ratio and unchanged checks, after `[placeholders]` are removed; placeholders are not allowed in revisions. Drafts over 500 characters or 1.6× the original (plus 60), equal to the original, or equal to an earlier draft are dropped. Only counts are logged.

## Caches

`ai_variants._CACHE` (32) keys on bullet, redacted job, requirement, keyword, category, goal, `VARIANT_PROMPT_VERSION`, model and keyword mode. `ai_keyword._CACHE` (16) keys on the full request (keyword, requirement, redacted job, entries, bullets, likely fits), category, revision, `KEYWORD_PROMPT_VERSION` and model. `skill_groups._CACHE` (64) keys on the canonical keyword, sorted group and tool names, `SKILL_PROMPT_VERSION` and model. Both are per process and cleared on restart.

## Invariants

- Suggestions never change the match score; the next deterministic match decides.
- No draft is saved without an explicit Accept, and the server reads the bullet from the placement.
- Missing tools are offered as Add to Skills, never as an AI rewrite.
- A new AI bullet uses only facts from its entry. Missing numbers are `[placeholders]` the user must replace before the server will save it.
- Skill group choice uses library, related-skills and hint data first. The model sees only group and tool names and can only pick a listed group or propose a new name.
- Skill group names are never hardcoded.
- Adding a skill writes to the library and the current resume only. Other resumes that include the group get a `composition_hidden_tools` row for a new or restored tool, so their payload, revision and history are untouched. A group newly added to the current resume shows only the added skill.

# Job match dashboard, AI coach and ATS score

The Job match tab is a dashboard rail beside the job description and the resume preview. The old "Review with AI" text block (`AiReviewBody`) is gone from the UI; `POST /ai-review` and its tests remain for compatibility.

## Files

| Path | Role |
|---|---|
| `frontend/src/match/useJobMatch.ts` | Jobs, selected job, deterministic match, `markRequirement`, `dismissRequirement`, `addTag`. Called once in `App.tsx`. |
| `frontend/src/match/MatchDashboard.tsx` | Sticky header (job, match score ring, counters, tabs) and the Overview tab. |
| `frontend/src/match/RequirementsTab.tsx`, `CoachTab.tsx`, `AtsTab.tsx` | The other three tabs. All panels stay mounted so results survive tab switches. |
| `frontend/src/match/MarkPopover.tsx` | Popover for a clicked highlight; a bottom sheet below 600px. |
| `frontend/src/matchMarks.ts` | Each mark carries `items`: keyword, group, matched or suggested, requirement, rewrite targets, Add to Skills. |
| `backend/app/ai_coach.py` | Whole-resume review: prompt, `filter_coach`, cache. |
| `backend/app/ats_score.py` | Deterministic ATS score, methodology and disclaimer. |

## Clickable highlights

Job description highlights (`JobDocument.tsx`) and resume highlights (`resume.html`, inside `{% if measure %}` only) are focusable buttons. The preview posts `resume-mark-click` with the match ids, the clicked line id and the element rect; `ResumePreview.tsx` maps the rect through the preview zoom. The popover shows Required / Preferred / Responsibility, Matched / Marked / Suggested, the requirement, and actions: Work into resume (for a missing keyword that isn't Skills-only; opens `KeywordAssistDialog`), Generate AI revision (opens the Suggest wording dialog on that bullet in keyword mode), Add to Skills, Show in dashboard, Show in the other document. A click on one resume line offers that line's revision first.

## Endpoints

| Route | Saves | Notes |
|---|---|---|
| `POST /api/job-descriptions/{job_id}/ai-coach` | nothing | Body `{composition_id}`. Returns `suggestions` (`rewrite`, `summary`, `add_skill`), `equivalents`, `revision`, `dropped`. |
| `POST /api/job-descriptions/{job_id}/ats-score` | nothing | Body `{composition_id, page_count}`. Returns `score`, `band`, `components`, `methodology`, `disclaimer`. |

Coach cards are accepted through existing endpoints: rewrites through `.../ai-variants/accept` (`draft` or `edited`), summaries through `/summaries/{id}/save` in `new` mode, skills through Add to Skills, equivalents through `markRequirement`.

## Coach filtering

The model sees the redacted posting, every requirement with its group and match state, the summary, and numbered placed bullets. The server keeps a suggestion only when its requirement matches a row exactly; rewrites and summaries pass `ai_variants.drop_reason` against the original text; `add_skill` names an unmatched keyword that `is_skill_keyword` accepts; bullet numbers are in range. At most 12 suggestions, required before preferred, then by priority; at most 8 equivalents, unmatched requirements only. Kept rewrites are registered with `remember_issued`, so accepting one unchanged sets `ai_generated`. Gated by `ai_available()` like the other AI modules. Cache: `ai_coach._CACHE` (16), keyed by posting, bullets, summary, requirements, revision, `COACH_PROMPT_VERSION` and model.

## ATS score

| Component | Points | Rule |
|---|---|---|
| Keyword match | 35 | Found keywords over all keywords; required count 2×, preferred 1×. |
| Required qualifications | 20 | Required-row coverage 60% + degree/years/certification gates 40% (pass 1, unknown 0.5, fail 0). |
| Job title alignment | 10 | Job title words found in display title, target role, or most recent job title. |
| Keyword context | 10 | Matched keywords evidenced in Experience, Projects or Leadership bullets. |
| Parseability | 15 | Experience, Education and Skills sections; email and phone; dated roles; −5 for the `sre` table template. |
| Length and bullets | 10 | ≤2 pages; bullets of 8–35 words; share of bullets with a number (full credit at 50%). |

Bands: Strong ≥ 75, Fair ≥ 55, otherwise Needs work. The UI always shows the disclaimer and re-scores when the revision or page count changes.

## Invariants

- The match score ring is 70% required coverage + 30% preferred coverage from the deterministic matcher. AI never changes it.
- The ATS score is deterministic and never uses AI.
- Coach suggestions save nothing until a card is accepted, and pass the same fabrication guard as single-bullet drafts.
- Nothing from the clickable-highlight code reaches the PDF render.

# AI in the editor's bullet dialogs

The Edit (pencil) and Switch (replace) buttons on a bullet in the main editor open dialogs with AI for one job. The job picker in each dialog shares its selection with the Job match tab (`useJobMatch`), so it defaults to the job linked to the resume.

## Files

| Path | Role |
|---|---|
| `backend/app/ai_variant_pick.py` | `pick_variants`: builds one slot per placed bullet with its library alternatives, scores them by job keywords, and asks the model to score them when AI is available. |
| `backend/app/job_repository.py` | `load_pick_inputs`: placements, parent labels and the active library bullets of those parents. |
| `backend/app/phase2j_repository.py` | `replace_placements`: switches several placements in one revision. |
| `frontend/src/editor/AiBulletTools.tsx` | Job picker, Tailor every bullet banner, AI draft panel, ranking badges, `LibraryReviewDialog`. |
| `frontend/src/editor/EditorLibraryDialogs.tsx` | `BulletEditDialog` (AI wording panel) and `BulletSwitchDialog` (ranked library, New wording with AI, Write new). |
| `tests/test_ai_variant_pick.py`, `tests/test_ai_variant_pick_api_integration.py` | Unit and database tests. |

## Endpoints

| Route | Saves | Notes |
|---|---|---|
| `POST /api/compositions/{cid}/ai-variant-pick` | nothing | Body: `job_id`, `placement_ids` (empty means every placed bullet), `use_ai`. Returns `slots` with `candidates` (current first before ranking), `best_key`, `recommend`, and `method` (`ai` or `keywords`). |
| `POST /api/compositions/{cid}/bullet-placements/replace-many` | placements | Body: `revision`, `items` of `placement_id`, `bullet_id`, `variant_id`. One revision. 422 when a bullet belongs to another entry, 409 for a duplicate bullet or a stale revision. |

New wording reuses `.../ai-variants` and `.../ai-variants/accept`, so drafts keep the same guardrails and provenance. In the Edit dialog, saving AI wording goes through accept (a new variant for this resume) instead of the save-mode chooser.

## Ranking

Candidates for a placement are the other active variants of its bullet plus unused bullets of the same role, project or school, capped at 8 per slot and 40 slots. Every candidate gets `keyword_hits` from `extract_keywords` on the job. With AI, the model scores each candidate 0 to 100 and gives a reason; it can only choose among library text, so there is no fabrication guard. A switch is recommended when the best AI score beats the current by `AI_MARGIN` (8), or, by keywords, when the best has more hits. An unused bullet is never recommended for two slots. When the model fails or scores nothing, the keyword ranking is returned with the error status. `ai_variant_pick._CACHE` (16) keys on the redacted job, slot candidates, `PICK_PROMPT_VERSION` and model.
