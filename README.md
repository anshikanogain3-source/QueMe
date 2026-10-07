# Virtual Interview Assistant

## Project Overview
Virtual Interview Assistant is a web-based platform designed to help students practice interviews, improve their communication and technical performance, and receive structured feedback based on their responses. The project is focused on creating a realistic interview preparation workflow for college students, with strong academic alignment to the Computer Science Department and student placement preparation.

The interview workflow remains a React/Vite prototype, but authentication and institutional access control are implemented for a configured Supabase project: versioned Postgres migrations, RLS, private Storage policies, real browser authentication, and server-side token validation are included.

## Main Users

### Student
- Authenticated users with an active student profile can access the student route.
- The current interview UI still uses local text answers, deterministic feedback, and a local report.

### Teacher / Class Coordinator
- Role routes are available. The database policies restrict records to explicit teacher and coordinator assignments.

### Admin
- Secure bootstrap and administrator-only user provisioning API endpoints are available.

## Main Features

### Student Prototype Features
- Supabase email/password and Google login, signup confirmation, password reset, logout, refresh/session-expiry handling, and role-protected routes
- Interview setup (Technical, HR, Behavioral, Role Based)
- An authenticated student workspace with an honest empty state until interview APIs are connected

### Teacher Features
- Teacher route is an explicit placeholder; no assigned-student data is exposed.

### Coordinator and Admin Features
- Separate route layouts exist; coordinator/admin routes remain explicit placeholders.

## Academic Structure

Computer Science Department

- MCA
- BCA
- B.Sc IT

The versioned Supabase schema models departments, courses, semesters, batches, classes, enrollment, teacher assignments, and scoped coordinator assignments.

## Interview Flow

Login
→ Dashboard
→ Interview Setup
→ Interview
→ Answer
→ Evaluation
→ Adaptive Next Question
→ Interview Completion
→ Report
→ Progress

## Current Project Status

### Currently implemented
- React + Vite browser application.
- Supabase Auth session handling, account confirmation, password reset, logout, and authoritative role lookup from `profiles`.
- Student, teacher, coordinator, and administrator role routes with no fabricated interview records.
- Login/signup/reset/Google UI connected to Supabase Auth when its public configuration is set.
- Teacher and admin routes are placeholder screens.
- FastAPI foundation with request IDs, uniform error/validation responses, liveness/readiness, and internal job submission.
- Postgres audio-job migration and worker queue with idempotency, leases, bounded retries, and timeouts. No audio processor is configured.
- Shared TypeScript/OpenAPI contracts.
- A reusable design-system foundation used by the landing page and application screens.

### Not implemented / not verified
- Live interview persistence, question generation, and audio analysis wiring in the dashboard (the schema, authorization, and private storage foundations are present).
- OpenAI-generated questions or adaptive model follow-ups.
- Speech, audio capture, transcription, recordings, and speech analysis.
- Persisting the dashboard/interview UI to the authorized database records.
- Server-persisted reports, generated-question audit history, or cross-device interview recovery.
- Production Docker deployment; local Compose was built and smoke-tested only.

### Current status summary
This project is currently a hybrid: identity, authorization, private storage, and the institutional schema are production-oriented; the interview dashboard remains a local prototype until it is connected to those records.

## Local Setup

### Frontend

Requires Node.js 22 and npm. Exact direct dependencies are pinned in `package.json` and `package-lock.json`.

```bash
npm ci
npm run dev
```

Set the public Supabase URL/key in the single root `.env` file (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`); Vite reads that root `.env` for the frontend. Vite starts on the first available local port (usually `http://localhost:5173`). Its `/api`, `/health`, and `/ready` paths proxy to `http://127.0.0.1:8000`. `VITE_*` values are public configuration only; never put secrets in them.

Routes: `/` is the public landing page (signed-in users are redirected to their role home), `/login`, `/signup`, `/forgot-password`, and `/reset-password` are the authentication screens.

### FastAPI Backend

Requires Python 3.10 or newer. From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.lock
```

The backend reads the single root `.env` file. Uncomment `QUEME_DATABASE_URL` there and set the password of a PostgreSQL instance, plus a random `QUEME_INTERNAL_API_TOKEN`. Start the API:

```bash
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

`GET /health` checks process liveness. `GET /ready` executes `SELECT 1`; it returns 503 until `QUEME_DATABASE_URL` points to a reachable database. `/docs` exposes the local FastAPI OpenAPI UI. The privileged internal job endpoint is disabled unless its server-only token is configured.

### Database and Compose

Uncomment `POSTGRES_PASSWORD` and `QUEME_INTERNAL_API_TOKEN` in the root `.env` and set local values. Then run:

```bash
docker compose up --build
```

Open `http://localhost:8080`. Compose initializes a local Postgres database and the audio-job migration. These local roles/database are development-only; they are not a substitute for configured Supabase Auth, RLS, or private Storage. To stop the stack, run `docker compose down`. Persistent database data is kept in the `queme-postgres` volume; remove it only when intentionally resetting local development data.

The optional worker profile is not enabled by default because no audio processor/model has been selected or configured. A real async processor module must be provided as `QUEME_AUDIO_PROCESSOR=package.module:function` before starting it:

```bash
docker compose --profile audio up --build audio-worker
```

Without a processor, worker startup fails explicitly; it does not create transcripts or claim analysis succeeded.

### Checks

```bash
npm run build
npm test
npm run typecheck:contracts
source .venv/bin/activate
python -m pytest -q
```

## Supabase setup

The single root `.env` holds all configuration: `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` for the frontend, and `QUEME_SUPABASE_URL`/`QUEME_SUPABASE_ANON_KEY` plus `QUEME_SUPABASE_SERVICE_ROLE_KEY` and a long `QUEME_BOOTSTRAP_SECRET` for the backend. Apply `supabase/migrations` with the Supabase CLI. The first administrator is created only through `POST /api/v1/admin/bootstrap` using the bootstrap secret; thereafter, an authenticated administrator uses `POST /api/v1/admin/users`. The service-role key and bootstrap secret must never be placed in a `VITE_*` variable.

Run the authorization suite with `bash supabase/tests/run_rls_tests.sh`. It checks anonymous denial, signup-metadata escalation, profile escalation, cross-student access, score writes, private-upload paths, and an unassigned teacher's access.

## Foundation Status

`frontend/` contains the React/Vite application and Supabase Auth client; `backend/` contains FastAPI token validation, signing, and administration endpoints; `workers/` contains the persistent Postgres job worker; `supabase/migrations/` contains the institutional schema and RLS; `shared/contracts/` contains TypeScript/OpenAPI contracts; and `deploy/` plus Compose provide the local stack.
