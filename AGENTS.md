# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Repository layout

Two independent apps in one repo, run as separate processes:

- `backend/` — FastAPI service (Python 3.12+), SQLite DB, runs on port 8000.
- `frontend/` — Next.js 16 (App Router) + React 19 + Tailwind v4 (TypeScript), runs on port 3000.

`backend/.env` holds runtime secrets (`SECRET_KEY` — required, fail-fast on startup; `GEMINI_API_KEY`; optional `CORS_ORIGINS`). LiveKit has been removed — no `LIVEKIT_*` keys are read. The frontend reads `NEXT_PUBLIC_API_URL` (defaults to `http://127.0.0.1:8000/api/v1`).

`PHASE1.md`–`PHASE10.md` and `PROJECT_PLAN.md` are historical design docs from incremental build-out of the product. They describe intent, not always current state — verify against code before treating any phase doc as authoritative.

## Common commands

Backend (run from `backend/`):
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000     # dev server, http://localhost:8000/docs for OpenAPI
```

Frontend (run from `frontend/`):
```bash
npm install
npm run dev      # next dev
npm run build    # next build
npm run lint     # eslint (flat config in eslint.config.mjs)
```

There is no test suite in either project. Don't claim tests pass — there's nothing to run.

## Architecture

### Backend (FastAPI)

`app/main.py` is the entrypoint. It uses a `lifespan` async context manager that calls `init_db()` (SQLAlchemy `create_all` — does NOT migrate existing tables) and idempotently seeds `DEFAULT_TOPICS` (SQLite `INSERT OR IGNORE`). CORS is restricted via `settings.CORS_ORIGINS` (default `http://localhost:3000,http://127.0.0.1:3000`).

Routers are mounted under `settings.API_PREFIX` (`/api/v1`):
- `auth` — recruiter signup/login, JWT issuance (see `app/core/security.py`); also issues short-lived candidate session tokens at registration.
- `interviews` — recruiter-side CRUD for interviews and their questions.
- `topics` — topic catalog (seeded at startup).
- `candidate` — candidate-facing flow: register, fetch interview by share link, upload answer audio/video (streamed in chunks with size + extension + MIME checks), transcribe, evaluate, fetch report. Uploads land in `backend/uploads/` resolved relative to the package root, not the CWD.
- `video` — serves recorded video for playback (recruiter-only with ownership check).

LiveKit was removed; there is no `voice` router and no `livekit_service`. The candidate-side voice flow is browser-only (Web Speech API + MediaRecorder via `frontend/src/hooks/useVoiceInterview.ts` — the name is historical).

Services in `app/services/` are the business-logic layer; routers should call into them rather than embedding logic:
- `speech_service.py` — `faster-whisper` (model `base`, CPU/int8) loaded lazily under a lock on first request; concurrent inference bounded by a semaphore. `transcribe_video` lazy-imports `moviepy` and uses try/finally to close the clip.
- `evaluation_service.py` — Gemini (`gemini-1.5-flash`) with `response_mime_type="application/json"` and a fence-stripping fallback. Failures raise instead of persisting dummy scores.
- `risk_engine.py` — proctoring/cheating-risk scoring fed by frontend signals (no module-level singleton; instantiate per-request).

Data model (`app/models/models.py`): `Recruiter` 1—* `Interview` 1—* `Question`; `Interview` 1—* `Candidate` 1—* `Answer`; `Answer` references both `Candidate` and `Question`. `Answer` carries two transcript fields — `transcript` (real-time Web Speech API from the browser) and `whisper_transcript` (server-side, higher-accuracy) — they are not interchangeable.

### Frontend (Next.js App Router)

`src/app/` routes:
- `/` — landing page.
- `/recruiter/login`, `/recruiter/dashboard`, `/recruiter/interview/...` — recruiter UI.
- `/interview/[link]` — candidate-facing interview at the shareable link. The candidate flow combines system check, voice verification, proctoring, and the live interview itself.

`src/services/api.ts` is the single API client; it stores the JWT in `localStorage` under `token`. Hooks under `src/hooks/` encapsulate browser-API-heavy logic that should not be inlined in components:
- `useSystemCheck` — camera/mic/screen permissions, internet speed.
- `useVoiceVerification` — records the gating phrase before the interview (UI-only check; no real STT verification).
- `useProctoring` — tab-switch / clipboard / focus signals feeding the risk engine. `useFaceDetection` / `useScreenTextDetection` are stubs (`isStub: true`); don't trust their numbers.
- `useVoiceInterview` — Web Speech API (TTS + recognition) + MediaRecorder. No LiveKit despite the name.

When adding browser-only features, gate `window`/`localStorage` access behind `typeof window !== 'undefined'` checks (the existing API client already does this) — App Router renders on the server by default and will crash otherwise.

## Conventions worth preserving

- New API endpoints go in a router under `app/routers/`, mounted in `main.py` with the shared `API_PREFIX`. Keep heavy logic in `app/services/` and call it from routers.
- Schemas in `app/models/schemas.py` (Pydantic) are separate from ORM models in `app/models/models.py` (SQLAlchemy). Don't return ORM objects directly from new endpoints — define a response schema.
- `SECRET_KEY` is mandatory and validated at startup (rejects empty / placeholder / <32 chars). Generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"`. Read from `settings.SECRET_KEY` — never hardcode.
- Tests live in `backend/tests/` (pytest). Dev deps: `backend/requirements-dev.txt` (`pytest`, `pytest-asyncio`, `httpx`). Run with `pytest backend/tests -q` from the repo root.
- `backend/ai_interviewer.db` is **gitignored** (`.gitignore: *.db`) — each developer's local DB lives only on their machine. `init_db()` creates the schema fresh on first boot. Schema changes via `create_all` will not migrate existing tables, so deleting the file is the standard way to pick up model changes locally.
