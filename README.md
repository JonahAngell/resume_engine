# Resume Engine

[Resume Engine](https://github.com/JonahAngell/resume_engine) is a web app for keeping one library of resume material and composing a different resume for each application. You edit reusable records once, choose what belongs on a resume, and preview or export that composition from a single HTML template.

It is for people who reuse the same profile, experience, projects, education, skills, and bullets across many roles, and who want each application to be a selection of that library.

## Workflow

1. Reusable records live in the library: profile, summary, education, skills, projects, employment, leadership, interests, custom sections, and bullets with wording variants and tags.
2. A resume is a composition. It selects which records to include, orders sections and entries, and places bullets. Each placement stores a wording snapshot for that resume. A later edit in the library can leave a placement outdated until you update it.
3. The editor autosaves the composition. A stale write returns a conflict so you can reload. Each successful save records an immutable revision. Restoring history creates a new revision and leaves earlier revisions in place.
4. Preview and PDF use the same template. Export PDF is available when the measured page count matches the resume’s target length.
5. Job descriptions are stored on their own. Job match compares the open resume with a posting. It reports which qualifications appear in the resume and its bullet tags, and it can add a missing keyword as a tag on a placed bullet. Bullet wording stays as placed.

## Screens

The rail is Home, Library, Jobs, and Bin.

- **Home** lists active resumes under My Resumes, with search and a list or card view. Open a resume, rename it, edit its details, duplicate it, or move it to the Bin. **Create New** starts a blank composition. **Import Existing Resume** reads a PDF, Word document (`.docx`), CSV, or ZIP — including a LinkedIn CSV export — into a draft you review before anything is saved.
- **Editor** is the composition workspace: Resume Details, section cards, bullet rows, undo and redo, revision history, and a live preview with zoom. Target length, date format, and template style are saved with the composition.
- **Reusable Library** (`#library`) is where entries and bullets are authored. It has list and card views, details, wording variants, tags, usage across resumes, and bulk actions. Edit in Library from the editor can return you to the same resume.
- **Jobs** (`#jobs`) stores job descriptions. Saving one extracts required and preferred keywords, and locations and salary when the posting states them.
- **Job match** is a tab in the editor. It scores the open resume against a job description and highlights matching lines in the preview. Choosing a job description in Resume Details links that job and copies its company and role onto the composition. A match request only returns the comparison. Clicking a missing keyword (other than a tool, which goes to Skills) offers **Work into resume**: AI wording that puts the keyword into existing bullets, or a new bullet for a role or project. Nothing saves until you accept, and new bullets can't be saved while they still have a `[placeholder]`.
- **Bin** is the Home view of archived resumes. Restore puts one back under My Resumes.

## Skill group and interest variants

Skill groups and interests can have variants, like other entries.

- A **skill group variant** has its own label and its own pick and order of the group's skills. For example, "Technical Languages" can have a "Data roles" variant labelled "Data Languages" that shows only Python and SQL.
- An **interest variant** is another wording of the interest.
- Each resume chooses which one to show from the **Variant** menu on the skill group or interest in the editor. "Original" is the record itself. The resume's own skill hiding and ordering still apply on top of a variant.
- Editing a skill group or interest in the editor asks how to keep the change:
  - **Overwrite** updates what the resume uses: the chosen variant, or the record itself. For a skill group that has no variant chosen, overwrite changes only the label.
  - **Create a new** makes a separate record. For a skill group, it copies the skills the resume currently shows.
  - **Save as a variant** saves the label and the skills shown, in order, as a new variant chosen for this resume.
- Manage variants on the Library record's **Variants** tab: add, edit, set **Use for new resumes** (the default), archive or restore.
  - New resumes start with the default variant.
  - A defaults set can choose a variant per record.
  - Archiving a variant clears its default. Resumes that already use it keep it, but it can't be chosen again until restored.
- API:
  - `POST /api/library/tool-groups/{id}/variants` with `name`, `group_name` and `tool_ids`
  - `POST /api/library/interests/{id}/variants` with `name` and `body`
  - `PUT /api/library/tool-group-variants/{id}` and `PUT /api/library/interest-variants/{id}`, where fields you leave out stay as they are and `is_default` sets or clears the default
  - `POST .../{id}/archive` and `POST .../{id}/restore`
  - `PUT /api/compositions/{id}/item-variant` with `revision`, `section`, `item_id` and `variant_id`, where `null` means the record itself
  - `POST /api/compositions/{id}/tool-groups/{group_id}/save` and `POST /api/compositions/{id}/interests/{interest_id}/save` for the save modes

## Templates

Preview and PDF both render [`backend/app/templates/resume.html`](backend/app/templates/resume.html). A composition picks one template style:

| Style | Label in the editor |
| --- | --- |
| `classic` | Default |
| `sheets` | Ruled Serif |
| `harvard` | Harvard Style |
| `dais` | Times Serif |
| `sre` | Skill Table |

Date format and section sort (automatic or manual) are applied on that same render path. PDF export sends the HTML to [Gotenberg](https://gotenberg.dev/).

### Custom templates

**Customize…** under Template (Resume Details) opens the template designer: settings on the left, a live preview of the open resume on the right. A custom template starts from one of the styles above, which supplies the layout and section names, and saves to the user's account under its own name. Any resume can then pick it from the Template list (marked ★).

| Setting | Range |
| --- | --- |
| Font | Arial, Carlito, Lato, Inter, EB Garamond, Tinos, Source Serif 4 (all but Arial are bundled in `backend/app/templates/fonts/`, SIL OFL) |
| Sizes | Name, section headings, job titles, body text, contact line (pt) |
| Colours | Text; name and headings; divider lines |
| Section headings | All caps or as written; bold or regular; no divider, a line below, or lines above and below |
| Entries | Bullet character; dates right-aligned or after the title; Tools as one line per group or a table |
| Page | Margins per side (0.3–1.25 in; bottom from 0.15 in), with Narrow, Normal, and Wide presets; line spacing 1.0–1.6; space after sections and bullets |

- Built-in styles stay read-only. A custom template that changes nothing renders exactly like its base: only settings that differ from the base produce CSS ([`backend/app/template_settings.py`](backend/app/template_settings.py)).
- Editing a template changes every resume linked to it. Each linked resume gets a new revision and a history entry that records the template's settings at that moment, so older revisions still preview as they looked. Deleting a template puts its resumes back on its base style, also with a history entry.
- The Tools layout can also be set per resume (Tools section → Layout); that choice beats the template's. A table on any template costs 5 points in the ATS score's parseability check, as the Skill Table style always has.
- API: `GET /api/templates` (templates plus fonts, bullets, base defaults and limits), `POST /api/templates`, `PUT /api/templates/{id}` (with `revision`; returns the open resume's new state when `composition_id` is sent), `DELETE /api/templates/{id}`, and `POST /api/templates/preview` (one resume rendered with unsaved settings). Resumes link through `template_id` and `tools_layout` on `PUT /api/compositions/{id}/preferences`; leaving either out keeps the current value.

## First-run seed

When the signed-in user has no compositions, the app imports [`seed/nia-calder-resume.json`](seed/nia-calder-resume.json) under the seed key `nia-calder-resume-v1`. That file is a fictional sample resume. The same seed key and file contents import once.

## Run locally

Docker Compose starts the API, PostgreSQL 17, and Gotenberg 8:

```bash
docker compose up --build
```

Open [http://localhost:8080](http://localhost:8080). On startup the API applies the SQL migrations in `backend/migrations/` and serves the built UI. `APP_ENV=local` signs requests in as the development user (`DEV_USER_ID` defaults to `local-user`). `GET /health` checks the process.

When `APP_ENV` is not `local`, the API resolves the user from a StudioShare session. Library and composition queries are scoped to that user on the server.

`APP_ENV=local` turns authentication off, so the API refuses to start in that mode when the database host is not local. Compose publishes the app on `127.0.0.1` only.

The API must run as a single worker (the Dockerfile passes `--workers 1`): the AI rate limits, the identity cache, and the AI caches live in process memory.

## Configuration

Copy [`.env.example`](.env.example) to `.env` for Compose. The API reads:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` / `STUDIOSHARE_DB_URL` | PostgreSQL connection. `STUDIOSHARE_DB_URL` wins when both are set. |
| `APP_ENV` | `local` signs every request in as the development user. |
| `DEV_USER_ID`, `DEV_USERNAME`, `DEV_DISPLAY_NAME`, `DEV_EMAIL` | The development user for `APP_ENV=local`. |
| `STUDIOSHARE_API_URL` | StudioShare user service, used to resolve the `access_token` cookie. |
| `ALLOW_BEARER_AUTH` | `true` also accepts `Authorization: Bearer` when there is no cookie. |
| `GOTENBERG_URL` | PDF renderer. Defaults to `http://gotenberg:3000`. |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_APP_URL` | Free OpenRouter models for AI features. |
| `STUDIOSHARE_AI_GATEWAY_URL`, `STUDIOSHARE_OIDC_TOKEN`, `STUDIOSHARE_OIDC_URL`, `STUDIOSHARE_AI_MODELS` | Studioshare AI Gateway, tried before OpenRouter. |
| `AI_RATE_PER_MINUTE`, `AI_DAILY_LIMIT` | Per-user AI request limits (defaults 20 and 300; `0` disables one). |
| `PORT` | Listen port in the image. Defaults to `8080`. |

## Repository layout

| Path | What it is |
| --- | --- |
| `frontend/` | React UI. The Docker image builds it, and the API serves `frontend/dist`. |
| `backend/app/main.py` | FastAPI app. The image runs `uvicorn app.main:app`. |
| `backend/migrations/` | Ordered SQL migrations, applied at startup in file-name order. Two files share the `020_` prefix; they were applied under those names, so they keep them. New files take the next unused number. |
| `backend/app/templates/resume.html` | Preview and PDF template. |
| `backend/app/template_settings.py`, `backend/app/templates_repository.py`, `backend/app/routers/templates.py` | Custom template settings, storage, and API. |
| `frontend/src/TemplateDesigner.tsx`, `frontend/src/templates.ts` | Template designer page and shared template types. |
| `backend/app/related_skills.yaml` | Clusters, aliases, and phrases used by job match. See [`docs/related-skills.md`](docs/related-skills.md). |
| `seed/` | Resume JSON used by import. |
| `tests/` | Pytest suite. Browser layout checks use Playwright (`npm run test:browser`). |
| `docker-compose.yml` | Local app, database, and Gotenberg. |
| `PROJECT_CONTEXT.md` | Identity, ownership, and schema contracts. |

Database integration tests need `TEST_DATABASE_URL` and permission to create and drop schemas. [`pytest.ini`](pytest.ini) puts `backend` on the Python path. Python dependencies are in [`backend/requirements.txt`](backend/requirements.txt). UI dependencies are in [`frontend/package.json`](frontend/package.json).
