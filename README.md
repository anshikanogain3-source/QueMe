# QueMe

QueMe is a campus virtual interview assistant. The backend is a Flask REST API backed by PostgreSQL. Its application factory registers the API blueprints, Flask-Migrate, CORS, and a database health endpoint.

## Backend setup

Requirements: Python 3.10+ and a running PostgreSQL server. Create an empty database and a database user, then use those credentials in `DATABASE_URL`.

From the repository root:

```bash
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Put the generated value in `.env` as `SECRET_KEY`. Replace the example database URL with the connection URL for your PostgreSQL database. Set a private `ADMIN_EMAIL` and an `ADMIN_PASSWORD` of at least 12 characters. The root `.env` is canonical; `backend/.env` is loaded only as a fallback for values missing from the root file.

Then install and initialize the backend from `backend/`:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app run.py db upgrade
flask --app run.py seed
flask --app run.py --debug run
```

Migration history is already checked in. Run `db upgrade` to create or update the schema; do not run `db init` or generate a duplicate initial revision. For future model changes, create a revision with `flask --app run.py db migrate -m "describe change"`, review it, and apply it with `flask --app run.py db upgrade`. Run migration and seed commands against the same `.env` and database used by the server.

Run `flask --app run.py db upgrade` from `backend/` to apply the checked-in schema, including the follow-up question field. Run `flask --app run.py seed` if the initial admin has not yet been created.

Backend workflow tests use an in-memory SQLite database and can be run from `backend/` with `python3 -m unittest discover -s tests -v`; they do not use the configured PostgreSQL database or call Groq/R2.

The `seed` command creates the first active admin using `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and `ADMIN_FULL_NAME`, plus default rubrics and score weights. Sign in on the frontend with that email and password. These values are used only when the admin is first created; rerunning `seed` does not change an existing admin password. Changing `ADMIN_PASSWORD` later does not reset it.

The API is served at `http://127.0.0.1:5000`; `GET /api/health` checks that the API can reach PostgreSQL. Authentication routes are under `/api/auth`, and admin routes are under `/api/admin`.

### Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | Yes | Random token signing key, at least 32 characters. |
| `DATABASE_URL` | Yes | PostgreSQL connection URL. |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | First seed | Initial active admin credentials; password must have at least 12 characters. |
| `ADMIN_FULL_NAME` | No | Display name for the initial admin. |
| `FRONTEND_ORIGIN` | No | Allowed browser origin; defaults to `http://localhost:5173`. |
| `SMTP_HOST`, `SMTP_FROM` | For password reset | SMTP server and sender address used to deliver reset links. |
| `SMTP_PORT` | No | SMTP port; defaults to 587 (STARTTLS). Set `SMTP_USE_SSL=true` for implicit TLS. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | No | SMTP credentials when authentication is required. |
| `JWT_EXP_HOURS` | No | Token lifetime; defaults to 24 hours. |
| `GROQ_API_KEY` | No | Enables Groq question drafting and rubric evaluation. |
| `GROQ_MODEL` | No | Groq model ID; defaults to `gpt-3.5-turbo`. |
| `WHISPER_MODEL` | No | faster-whisper model name; defaults to `base`. |
| `STORAGE_BACKEND` | No | `local` by default, or `r2` for Cloudflare R2. |
| `STORAGE_LOCAL_DIR` | No | Local answer storage directory; defaults to `backend/uploads`. |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` | Only for R2 | Cloudflare R2 account, credentials, and bucket. |

Groq is optional: without a key, interviews still complete but automated content scores and follow-up generation are omitted and reports are flagged for teacher review. faster-whisper is included in `backend/requirements.txt`; its configured model is downloaded/loaded on the first audio submission, so first use may take longer and needs network access. If transcription is unavailable, the recording remains stored and the report requests teacher review. R2 is optional; local storage is the default. With `STORAGE_BACKEND=r2`, all four R2 settings above are required, and private answer playback is served through the authenticated API.

## Frontend setup

In a second terminal, from `frontend/`:

```bash
npm install
npm run dev
```

Open the local Vite address (normally `http://127.0.0.1:5173`). Vite proxies `/api` requests to Flask on port 5000. Use a current Chrome, Edge, or Firefox browser and allow microphone access. Question speech uses the browser's speech synthesis; question text remains visible if speech synthesis is unavailable. Faster-whisper loads its configured model on the first answer upload and may need to download that model once.

### Role dashboards

- Students see assigned interviews, continue sessions, and view completed reports and their saved recordings.
- Teachers see their assigned sessions and can open completed reports to score answers, add per-question or overall remarks, and set per-question or overall score overrides.
- Admins can approve/reject and filter student/teacher accounts, review campus analytics and reports needing review, adjust score weights, open recent reports, and download per-report or all-report exports.

## Account and admin endpoints

- `POST /api/auth/register` accepts `full_name`, `email`, `password`, `role` (`student` or `teacher`), `course_id`, `semester` (`1st`–`8th`), and `academic_year`. Course and class group are required for both roles; `roll_number` and `employee_id` are optional. New accounts are always `PENDING`.
- `POST /api/auth/login` returns a bearer token only for `ACTIVE` accounts. `GET /api/auth/me` returns the authenticated account.
- `POST /api/auth/forgot-password` accepts an email and sends a reset link when an account exists. Configure `SMTP_HOST` and `SMTP_FROM` (and SMTP credentials if needed) to enable delivery. Links expire after 30 minutes. `POST /api/auth/reset-password` accepts the link's `token` and a new password of at least 12 characters.
- `GET /api/admin/courses` lists BCA, MCA, and BSC IT; `GET /api/admin/semesters` lists configured course-semester-academic-year class groups. These are public for registration. Admins create class groups with `POST /api/admin/semesters` and `{ "course_id": 1, "semester": "1st", "academic_year": "2026–27" }`. The legacy department/batch table names remain internal compatibility names; teacher batch assignments now mean exact course-semester-year groups.
- Admin-only account routes: `GET /api/admin/pending-users`, `GET /api/admin/users` (optional `role` and `account_status` filters), and `POST /api/admin/users/<user_id>/status` with `{"account_status":"ACTIVE"}` or `{"account_status":"REJECTED"}`.
- Admin-only settings route: `GET` or `PATCH /api/admin/settings` with `content_weight` and/or `delivery_weight`. Values must be between 0 and 1 and sum to 1.0.
- `GET /api/admin/analytics` and `GET /api/admin/reports.xlsx` are admin-only.
- `GET /api/admin/reports` lists up to 100 recent reports for the admin dashboard; individual reports also have PDF and Excel downloads.

API errors use a JSON object with an `error` message and a stable `code` field. Admin requests require `Authorization: Bearer <token>`.

## Student interview endpoints

- `GET /api/interviews` lists interviews assigned to the signed-in student.
- `GET /api/interviews/<id>` returns the current session state and question.
- `POST /api/interviews/<id>/start` requires `{"consent": true}` and moves a scheduled interview into progress.
- `POST /api/interviews/<id>/questions/<interview_question_id>/answer` accepts multipart form data with an `audio` file. The server stores answer audio through the configured local/R2 storage provider, transcribes it with word timestamps when faster-whisper is available, checks recording quality, and calculates delivery metrics. Usable transcripts and audio metrics are evaluated against the assigned rubric with Groq when configured. A usable answer may receive one Groq-generated follow-up; unavailable transcription or Groq leaves the session usable and flags the answer for teacher review.
- `POST /api/interviews/<id>/advance` accepts `{"intent":"REPEAT"}`, `{"intent":"SKIP"}`, or `{"intent":"DONE"}` for explicit controls. `REPEAT` keeps the current question, `SKIP` advances one question, and `DONE` ends the interview immediately. Spoken commands are recognized only when the entire transcript matches a supported command phrase.
- `GET /api/interviews/<id>/questions/<interview_question_id>/audio` streams a stored answer only to the student, assigned teacher, or admin with an active bearer token.
- Completing an interview immediately creates or refreshes its report. `GET /api/interviews/<id>/report` returns scores, feedback, review flags, and answer details to the student, assigned teacher, or admin. `PATCH` on the same route lets the assigned teacher or admin add remarks and question or overall score overrides.
- `GET /api/interviews/<id>/report.pdf` and `GET /api/interviews/<id>/report.xlsx` export an individual report for its student, assigned teacher, or admin. `GET /api/admin/reports.xlsx` exports all reports to admins.

Reports state that QueMe’s AI feedback supports practice and learning. It is decision support, not a final placement decision, and should be considered alongside teacher review. The notice appears on the report screen, in PDFs, and on the Guidance worksheet in Excel exports.

Answer uploads are limited to 25 MB. Reports use `NEEDS_REVIEW` when an answer lacks a usable transcript, automated rubric evaluation is unavailable, an answer was skipped, or no score could be calculated. Teacher overrides become the final score and appear in both exports.

## Teacher authoring endpoints

All authoring routes require an active teacher bearer token.

- Teacher workspace routes: `GET /api/teacher/analytics` returns teacher-scoped interview, student, review, and average-score counts; `GET /api/teacher/students?batch_id=<id>` lists active students in the selected class group for assignment.
- `GET/POST /api/questions` list/create questions; `GET/PUT/PATCH/DELETE /api/questions/<id>` read or manage a teacher-owned question. Use `POST /api/questions/generate` with `topic`, `question_type`, and `difficulty` to get up to 10 Groq drafts. In Create interview, teachers review/edit and select drafts; adding selected drafts calls `POST /api/questions/commit-drafts`, which saves them to that teacher's reusable question bank and reuses an existing question when normalized text matches. The returned question IDs are added to the template selection; removing them from that template does not delete library records. If Groq is unavailable, the endpoint returns `manual_fallback: true` and manual CRUD remains available.
- `GET/POST /api/rubrics` list/create rubrics; `GET/PUT/PATCH/DELETE /api/rubrics/<id>` read or manage teacher-owned rubrics. The four admin-seeded rubrics are available for use but read-only.
- `GET/POST /api/templates` list/create templates. A template body includes `title`, optional `description` and `duration_minutes`, and an ordered `questions` array such as `[{"question_id": 12, "rubric_id": 3}]`. Array order becomes question order. Read, update, and delete with `GET/PUT/PATCH/DELETE /api/templates/<id>`.
- `POST /api/interviews` assigns a teacher-owned template. Send `template_id` and exactly one of `student_id` or `batch_id` (the selected course-semester-year class group); optional `scheduled_at` is ISO-8601. Class-group assignment creates one scheduled interview per active student and copies the ordered template questions and rubrics into each interview. `GET /api/interviews` lists the signed-in teacher's assignments or the signed-in student's assigned interviews.
- A teacher can cancel a scheduled assignment with `POST /api/interviews/<id>/cancel`. Interviews already in progress or completed cannot be cancelled. Completed sessions link to the existing authorized report/review and PDF/Excel export routes.

Questions, rubrics, and templates already used in interviews are protected from edits/deletion that could change historical records. Deactivate an old question instead of deleting it.

