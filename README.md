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
| `backend/app/related_skills.yaml` | Clusters, aliases, and phrases used by job match. See [`docs/related-skills.md`](docs/related-skills.md). |
| `seed/` | Resume JSON used by import. |
| `tests/` | Pytest suite. Browser layout checks use Playwright (`npm run test:browser`). |
| `docker-compose.yml` | Local app, database, and Gotenberg. |
| `PROJECT_CONTEXT.md` | Identity, ownership, and schema contracts. |

Database integration tests need `TEST_DATABASE_URL` and permission to create and drop schemas. [`pytest.ini`](pytest.ini) puts `backend` on the Python path. Python dependencies are in [`backend/requirements.txt`](backend/requirements.txt). UI dependencies are in [`frontend/package.json`](frontend/package.json).
