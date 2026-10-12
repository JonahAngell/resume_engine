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
- **Job match** is a tab in the editor. It scores the open resume against a job description and highlights matching lines in the preview. Choosing a job description in Resume Details links that job and copies its company and role onto the composition. A match request only returns the comparison.
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

When the signed-in user has no compositions, the app imports [`seed/nia-calder-resume.json`](seed/nia-calder-resume.json) under the seed key `nia-calder-resume-v1`. That file is a fictional sample resume. The same seed key and file contents import once. [`seed/jonah-resume.json`](seed/jonah-resume.json) is also in the repository; the product default is the Nia Calder file.

## Run locally

Docker Compose starts the API, PostgreSQL 17, and Gotenberg 8:

```bash
docker compose up --build
```

Open [http://localhost:8080](http://localhost:8080). On startup the API applies the SQL migrations in `backend/migrations/` and serves the built UI. `APP_ENV=local` signs requests in as the development user (`DEV_USER_ID` defaults to `local-user`). `GET /health` checks the process.

When `APP_ENV` is not `local`, the API resolves the user from a StudioShare session. Library and composition queries are scoped to that user on the server.

## Repository layout

| Path | What it is |
| --- | --- |
| `frontend/` | React UI. The Docker image builds it, and the API serves `frontend/dist`. |
| `backend/app/main.py` | FastAPI app. The image runs `uvicorn app.main:app`. |
| `backend/migrations/` | Ordered SQL migrations, applied at startup. |
| `backend/app/templates/resume.html` | Preview and PDF template. |
| `backend/app/related_skills.yaml` | Clusters, aliases, and phrases used by job match. See [`docs/related-skills.md`](docs/related-skills.md). |
| `seed/` | Resume JSON used by import. |
| `tests/` | Pytest suite. Browser layout checks use Playwright (`npm run test:browser`). |
| `docker-compose.yml` | Local app, database, and Gotenberg. |
| `PROJECT_CONTEXT.md` | Identity, ownership, and schema contracts. |

Database integration tests need `TEST_DATABASE_URL` and permission to create and drop schemas. [`pytest.ini`](pytest.ini) puts `backend` on the Python path. Python dependencies are in [`backend/requirements.txt`](backend/requirements.txt). UI dependencies are in [`frontend/package.json`](frontend/package.json).
