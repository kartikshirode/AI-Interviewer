# PROJECT_CONTEXT

A research-grade brief on the AI Interviewer codebase. Written 2026-05-08
against commit `f1ff018`. If anything here disagrees with the code, **trust
the code** — this doc captures intent and history; behavior is in the files.

`README.md` is the user-facing setup guide (slightly stale on a few details
— LiveKit references). `CLAUDE.md` is the LLM-agent instruction file.
`PHASE1.md` … `PHASE10.md` and `PROJECT_PLAN.md` are *historical* design
docs; don't trust them as ground truth.

---

## 1. At a glance

**AI Interviewer** is a self-serve technical-interview platform for
recruiters. A recruiter creates an interview (role, difficulty, topics,
skills), shares a link, and a candidate goes through:

1. System check (camera/mic/screen permissions, internet ping).
2. Voice verification (gating phrase — UI-only, see §10).
3. AI-led interview: an AI asks questions verbally, candidate answers by
   voice, audio + (eventually) screen are recorded, proctoring signals are
   collected.
4. After the candidate completes, the recruiter triggers transcription
   (faster-whisper) and evaluation (Gemini), then views a scored report.

**Stack:** FastAPI + SQLAlchemy + SQLite (backend) | Next 16 App Router +
React 19 + Tailwind v4 + TypeScript (frontend) | faster-whisper (local STT)
| Google Gemini (`gemini-flash-latest`) for question generation and answer
evaluation | browser Web Speech API for live transcripts and TTS.

**Lifecycle:** pre-launch / active development. Single-developer project.
Dev DB (`backend/ai_interviewer.db`) is checked in for convenience. There
is no migration tooling — `init_db()` runs `create_all()` only.

---

## 2. Repository layout

```
AI-Interviewer/
├── backend/
│   ├── app/
│   │   ├── main.py                       # FastAPI entrypoint, lifespan, CORS, topic seeding
│   │   ├── core/
│   │   │   ├── config.py                 # pydantic-settings; SECRET_KEY validator
│   │   │   ├── database.py               # SQLAlchemy engine, Base, get_db
│   │   │   └── security.py               # bcrypt, JWT helpers (recruiter + candidate tokens)
│   │   ├── models/
│   │   │   ├── models.py                 # SQLAlchemy ORM
│   │   │   └── schemas.py                # Pydantic request/response
│   │   ├── routers/
│   │   │   ├── auth.py                   # signup, login, get_current_recruiter, get_current_candidate
│   │   │   ├── interviews.py             # CRUD + sample-questions previews + bank resolver
│   │   │   ├── topics.py                 # topic CRUD + general-skills endpoint
│   │   │   ├── candidate.py              # public-ish candidate flow + recruiter-only mgmt
│   │   │   └── video.py                  # recruiter-only video file streaming
│   │   └── services/
│   │       ├── question_generator.py     # Gemini prompt → JSON questions, with static fallback
│   │       ├── skills.py                 # GENERAL_SKILLS, normalize_skills_key/list
│   │       ├── speech_service.py         # faster-whisper, lazy-loaded, semaphore-bounded
│   │       ├── evaluation_service.py     # Gemini answer scoring with markdown-fence-tolerant JSON parse
│   │       └── risk_engine.py            # proctoring → cheating-risk score (per-request)
│   ├── tests/                            # pytest; 34 cases, in-memory SQLite via StaticPool
│   ├── ai_interviewer.db                 # dev DB (checked in)
│   ├── requirements.txt                  # prod deps
│   ├── requirements-dev.txt              # pytest, pytest-asyncio, httpx
│   └── .env                              # SECRET_KEY (mandatory) + GEMINI_API_KEY (gitignored)
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx                  # landing
│   │   │   ├── recruiter/
│   │   │   │   ├── login/                # signup + login on the same page
│   │   │   │   ├── dashboard/            # interview create form, list, copy link
│   │   │   │   └── interview/[id]/candidates/  # candidate list + report
│   │   │   └── interview/[link]/         # candidate-side interview UI
│   │   ├── hooks/
│   │   │   ├── useSystemCheck.ts         # device perms, speed test
│   │   │   ├── useVoiceVerification.ts   # gating phrase recorder (UI-only verification)
│   │   │   ├── useProctoring.ts          # tab/clipboard/focus signals + stub face/text detection
│   │   │   └── useVoiceInterview.ts      # Web Speech API + MediaRecorder (name is historical)
│   │   └── services/
│   │       └── api.ts                    # single API client; recruiter + candidate token storage
│   ├── package.json                      # next 16.2.5, react 19, tailwind v4
│   ├── next.config.ts                    # security headers
│   └── eslint.config.mjs                 # flat config
├── PHASE1.md … PHASE10.md, PROJECT_PLAN.md   # historical, not authoritative
├── README.md                             # user-facing (slightly stale: still mentions LiveKit)
├── CLAUDE.md                             # instructions for the LLM agent
└── PROJECT_CONTEXT.md                    # this file
```

**Run dev:**

```bash
# Backend (from backend/)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000      # http://localhost:8000/docs

# Frontend (from frontend/)
npm install
npm run dev                                    # http://localhost:3000
```

**Required env (`backend/.env`):**

| Var | Required | Notes |
|---|---|---|
| `SECRET_KEY` | yes | Pydantic `field_validator` rejects empty / placeholder / <32 chars at startup. Generate: `python -c "import secrets; print(secrets.token_urlsafe(64))"`. |
| `GEMINI_API_KEY` | for AI features | Without it, generator and evaluator both fall back to static / error paths. |
| `CORS_ORIGINS` | optional | Comma-separated. Default `http://localhost:3000,http://127.0.0.1:3000`. |
| `MAX_UPLOAD_SIZE` | optional | Default 50 MB. Captured at function-default-arg time — doesn't react to runtime overrides (mild quirk, not a bug in production). |
| `DATABASE_URL` | optional | Default `sqlite:///./ai_interviewer.db`. |

`Settings.Config.extra = "ignore"` so stale env keys (e.g. old `LIVEKIT_*`)
don't crash startup.

**Frontend env:** `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8000/api/v1`).

---

## 3. Backend architecture

### Entrypoint — `app/main.py`

- FastAPI app constructed with a `lifespan` async context manager (the
  deprecated `@app.on_event` was removed in the swarm-audit fixes).
- On startup: `init_db()` runs `Base.metadata.create_all()` — creates new
  tables, **does not migrate existing tables**. Then `_seed_default_topics()`
  inserts the 8 seeded topics (`Python`, `Machine Learning`, `NLP`,
  `Statistics`, `SQL`, `Data Structures`, `Deep Learning`, `System Design`)
  via SQLite `INSERT OR IGNORE`, then refreshes their curated `skills` lists
  on every boot — so the catalog tracks code without a DB drop.
- CORS allow-list comes from `settings.cors_origin_list()`. The earlier
  `allow_origins=["*"]` + `allow_credentials=True` combo was killed during
  the audit.
- Routers mounted under `settings.API_PREFIX = "/api/v1"`: `auth`,
  `interviews`, `topics`, `candidate`, `video`. **No `voice` router** — see
  §12 LiveKit decision.

### Authentication — `app/core/security.py` + `app/routers/auth.py`

Two separate token types, both JWT (HS256):

- **Recruiter access token** — issued at `POST /auth/login`. Long-lived
  (default 30 min, configurable). Stored on the frontend in `localStorage`
  as `token`. Carries `{sub, id, exp}`.
- **Candidate session token** — issued at `POST /candidate/interview/{id}/
  register`. Stored on the frontend in `sessionStorage` as
  `candidate_token`. Carries `{candidate_id, interview_id, exp}` (4 hours).

Two FastAPI dependencies:

- `get_current_recruiter(token = Depends(oauth2_scheme))` → reads `Authorization:
  Bearer <jwt>`, looks up the recruiter, gates recruiter-only endpoints.
- `get_current_candidate(authorization: Optional[str] = Header(None))` →
  reads the same header but parses it as a candidate token; verifies
  `candidate.interview_id` matches the token claim.

Login is timing-equalized: even when no recruiter exists for the email,
`dummy_verify_password` is run so bcrypt cost is paid on both branches.

### Routers

- **`auth.py`** — signup (`POST /auth/signup`, returns `RecruiterResponse`),
  login (`POST /auth/login`, returns `{access_token, token_type}`).
- **`topics.py`** — `POST /topics/` (recruiter auth, persists `skills`),
  `GET /topics/` (public list), `GET /topics/{id}` (public detail), and
  `GET /topics/general-skills` returning the soft-skill list.
- **`interviews.py`** — recruiter-only CRUD plus the **bank-first question
  resolver** (§6) and two preview endpoints:
  - `GET /interviews/sample-questions/{topic_id}?difficulty=&count=&regenerate=&skills=…`
  - `GET /interviews/sample-questions/by-name/{topic_name}?…` (for the
    custom "Other" topic branch).
- **`candidate.py`** — split into three blocks by auth model:
  - **Public**: `GET /candidate/interview/{link}` (look up by share link),
    `POST /candidate/interview/{id}/register` (issues candidate session
    token).
  - **Candidate-token**: `GET …/questions`, `POST …/start`, `POST /answer`
    (Form upload, streamed in 1 MiB chunks with extension allowlist
    `.webm/.wav/.mp3/.m4a/.ogg/.oga` for audio + `.webm/.mp4/.mkv/.mov/.avi`
    for video, MIME prefix check `audio/`, `video/`, size cap from
    `settings.MAX_UPLOAD_SIZE`), `POST …/complete`. The answer-submit
    response is shaped by `AnswerSubmittedResponse` so server filesystem
    paths don't leak to the candidate.
  - **Recruiter-token**: per-answer transcribe, per-candidate transcribe-all
    (returns 207 on partial failure), per-candidate evaluate, proctoring
    save+report, full report. Each enforces ownership via
    `_ensure_owns_candidate`.
- **`video.py`** — `GET /videos/{answer_id}` returns the recorded video
  file. Recruiter-auth-gated; ownership-checked. Returns 404 (not 403) on
  not-owned to avoid enumeration.

### Services

- **`question_generator.py`** — `QuestionGenerator(fallback_provider)`. Calls
  Gemini with a difficulty-aware, skills-aware prompt; expects a JSON
  array; tolerates `\`\`\`json` markdown fences. **No in-memory cache** —
  the database (`QuestionBank`) owns persistence now (§6). On any failure
  (no API key, exception, unparseable response) it returns the result of
  the fallback provider, which is the static `SAMPLE_QUESTIONS_BY_DIFFICULTY`
  dict embedded in `interviews.py`.
- **`skills.py`** — `GENERAL_SKILLS` constant (Communication, Problem
  solving, Team management, Leadership, Ownership, Collaboration), plus
  `normalize_skills_key(skills)` (sorted, lowercased, comma-joined — used
  as the bank lookup key) and `normalize_skills_list(skills)` (deduped,
  trimmed; preserves casing from first occurrence).
- **`speech_service.py`** — `faster-whisper` model `base`, CPU/int8.
  Loaded **lazily under a lock** on first request; concurrent inference
  bounded by `threading.Semaphore(2)`. `transcribe_video` lazy-imports
  `moviepy` and uses `try/finally` to close the clip + delete the temp
  audio file. There's also `transcribe_audio_async` that wraps the sync
  call in `asyncio.to_thread`.
- **`evaluation_service.py`** — Gemini (`gemini-flash-latest`) with
  `response_mime_type="application/json"` and a fence-stripping fallback.
  Returns a `_ok` flag; the candidate router raises HTTP 502 on failure
  rather than persisting dummy scores. **Rubric is technical-only right
  now** — see §10 open problem.
- **`risk_engine.py`** — proctoring/cheating-risk scoring. **Per-request,
  not a singleton** (the previous module-level instance had thread-safety
  bugs).

---

## 4. Frontend architecture

### App Router routes — `src/app/`

- `/` — landing.
- `/recruiter/login` — combined login + signup.
- `/recruiter/dashboard` — main recruiter UI: list interviews, create new
  interview (the rich form with topic chips + per-topic skills cards + AI
  preview), copy share link.
- `/recruiter/interview/[id]/candidates` — candidate list + per-candidate
  report.
- `/interview/[link]` — the entire candidate-side flow: register → system
  check → voice verification → live interview → completed.

### Hooks — `src/hooks/`

- **`useSystemCheck`** — camera/mic/screen permissions via
  `getUserMedia`/`getDisplayMedia`; latency probe via Cloudflare's
  `cdn-cgi/trace`. `detectDevice` runs as a `useState` lazy initializer to
  satisfy React 19's `react-hooks/immutability` rule.
- **`useVoiceVerification`** — records a gating phrase, plays it back. **No
  real STT verification** — just a UI gate. Open follow-up.
- **`useProctoring`** — real signals: `visibilitychange` (tab switch),
  clipboard read attempts, blur/focus events. `useFaceDetection` and
  `useScreenTextDetection` are stubs that expose `isStub: true`; their
  numbers are placeholder. Don't use them for risk scoring.
- **`useVoiceInterview`** — Web Speech API (TTS via `SpeechSynthesis`,
  recognition via `SpeechRecognition`/`webkitSpeechRecognition`) plus
  `MediaRecorder` for background audio capture. **Despite the name, no
  LiveKit** — the name is historical from when LiveKit was being trialed.

### API client — `src/services/api.ts`

- Single `ApiService` instance. Two separate token slots: recruiter
  `token` in `localStorage`, candidate `candidate_token` in
  `sessionStorage`. Calls accept `useCandidateToken: true` to swap.
- `formatApiError(body, status)` flattens FastAPI 422 validation responses
  (`detail: [{loc, msg, type}, …]`) to readable strings — fixes the
  `[object Object]` issue that surfaced when the password-min-length
  validator started rejecting short passwords.
- Skills-aware sample-question helpers:
  - `getSampleQuestions(topicId, difficulty, { count, regenerate, skills })`
  - `getSampleQuestionsForCustomTopic(topicName, difficulty, { count, regenerate, skills })`
  - `getGeneralSkills()` returns the soft-skill list.

---

## 5. Data model

ORM in `backend/app/models/models.py`. Pydantic schemas in
`backend/app/models/schemas.py`. The two are deliberately separated — never
return ORM objects from new endpoints; define a response schema.

```
Recruiter ──< Interview ──< Question ──< Answer >── Candidate
                          (topic_id ─── Topic)
                                                        ↑ many-to-one back to Interview

QuestionBank   (standalone, keyed by string topic_name + difficulty + skills_key)
```

### Tables

- **`recruiters`** — `id`, `email` (unique, indexed), `hashed_password`,
  `full_name`, `company`, `created_at`. Cascades into interviews on delete.
- **`topics`** — `id`, `name` (unique, indexed), `description`, **`skills`
  (JSON list)**. The 8 seeded topics get curated skill catalogs from
  `DEFAULT_TOPICS` in `app/main.py`.
- **`interviews`** — `id`, `recruiter_id` (FK + index, ON DELETE CASCADE),
  `role`, `difficulty`, `num_questions`, `interview_link` (unique UUID),
  `status`, **`skills` (JSON list)**, `created_at`, `expires_at`. Cascades
  into questions + candidates on delete.
- **`questions`** — `id`, `interview_id` (FK CASCADE, indexed), `topic_id`
  (FK nullable, indexed), `question_text`, `source` (`"system"` /
  `"recruiter"`), `created_at`. `topic_id` is nullable because custom
  ("Other") topic questions don't link to a `Topic` row — the catalog
  stays curated.
- **`candidates`** — `id`, `interview_id` (FK CASCADE, indexed), `name`,
  `email`, `status`, `final_score`, `communication_score`, `cheating_risk`,
  `created_at`. **Unique constraint on `(interview_id, email)`** prevents
  re-registration spam.
- **`answers`** — `id`, `candidate_id` (FK CASCADE, indexed), `question_id`
  (FK CASCADE, indexed), **`transcript`** (real-time Web Speech API),
  **`whisper_transcript`** (server-side, higher-accuracy — *not
  interchangeable* with the above), `audio_path`, `video_path`,
  `correctness`, `clarity`, `depth`, `confidence_score`, `feedback`,
  `is_flagged`, `flag_reason` (now also set by background transcription
  failures: `"transcription_failed"`, `"transcription_empty"`,
  `"audio_missing"`), `created_at`. **Unique constraint on `(candidate_id,
  question_id)`** prevents duplicate-answer races.
- **`question_bank`** (new in `f1ff018`) — `id`, **`topic_name` (str,
  indexed)**, **`difficulty` (str, indexed)**, **`skills_key` (str,
  indexed — normalized form: lowercased, sorted, comma-joined)**,
  `skills_json` (JSON, original list for display), `question_text` (text),
  `source` (`"gemini"` / `"static"` / `"manual"`), `times_used` (int),
  `created_at`, `last_used_at`. Composite index on `(topic_name,
  difficulty, skills_key, times_used)` powers the hot lookup. Unique
  constraint on `(topic_name, difficulty, skills_key, question_text)`
  dedupes identical generations.

`topic_name` is a string, **not** an FK to `topics.id`, so questions for
custom "Other" topics persist alongside the catalog ones.

### Schema migration model

There is **no migration tool**. `init_db()` only `create_all`s. To pick up
new columns or tables in dev, **delete `backend/ai_interviewer.db`** and
restart. CLAUDE.md documents this. The user has been explicitly informed
in commits that touched schema.

`Topic.skills` and `Interview.skills` were added with `default=list`, so
existing rows on a non-dropped DB get `[]` automatically — no NULL pain.
The `_seed_default_topics()` UPDATE pass refreshes the seeded topics' skill
lists every boot, so the curated catalog tracks code even if the DB wasn't
dropped.

---

## 6. Question pipeline

Lives in `backend/app/routers/interviews.py`. Three layers:

```
recruiter creates interview / previews topic
          │
          ▼
  _resolve_questions(db, topic_name, difficulty, skills, count, force_refresh)
          │
          │  skills_list = normalize_skills_list(skills)
          │  skills_key  = normalize_skills_key(skills_list)
          │
          ├── force_refresh? ─── no ──► query QuestionBank ordered by
          │                              (times_used asc, random())
          │                              limit count*3
          │                              │
          │                              ├── pool.size >= count?
          │                              │       │
          │                              │       └── random.sample(pool, count)
          │                              │           bump times_used / last_used_at
          │                              │           return ([qs], "bank-hit")     ◄── ZERO Gemini calls
          │                              │
          │                              └── else fall through ▼
          ▼
  generator.generate(topic_name, difficulty, skills_list, count)
          │
          ├── Gemini configured?
          │       │
          │       ├── yes ─► call gemini-flash-latest with JSON-only prompt
          │       │           parse / fence-strip / shape-coerce
          │       │           returns ([qs], "gemini")
          │       │
          │       └── no  ─► fall back ▼
          │
          └── static SAMPLE_QUESTIONS_BY_DIFFICULTY[topic_name][difficulty]
              returns ([qs], "static")
          │
          ▼
  _persist_to_bank(db, topic_name, difficulty, skills_key, skills_list, qs, source)
          │   one query for existing question_texts in this bucket → skip dupes
          │   insert each new row; rollback on IntegrityError (concurrent writer race)
          ▼
  return (qs[:count], source)
```

Key properties:

- **Bank cache is global, persistent, free.** Recruiter A's "Python /
  medium / [asyncio]" generation seeds recruiter B's interviews. The bank
  is the system-of-record for previously generated questions.
- **`force_refresh=True`** (the UI's *Regenerate* button) skips the bank
  read but still persists the new generation, so the bank only ever grows.
- **`times_used asc`** means the bank spreads coverage — the same five
  questions don't dominate just because they were generated first. Random
  sample within the pool means different interviews with the same key
  don't get identical sets, so candidates can't trivially share answers.

---

## 7. Skills + difficulty dimensions

The `(topic, difficulty, skills)` tuple drives both bank lookups and Gemini
prompts.

- **Difficulty:** `"easy"` / `"medium"` / `"hard"`. Stored on the
  `Interview` row, passed into both the question prompt (calibrates depth)
  and the evaluation prompt (calibrates strictness). The static fallback
  bank has separate easy/medium/hard buckets for each seeded topic.
- **Skills:** free-text list. `Topic.skills` is the curated per-topic list
  (e.g. `Python` → `["asyncio", "decorators", "typing", "performance",
  "OOP", "generators", "dataclasses"]`). `GENERAL_SKILLS` (in
  `services/skills.py`) is the soft-skill list shown alongside every topic.
  The recruiter chips select any combination; the union flattens into
  `Interview.skills` (one list per interview) and into each preview
  request's lookup key.
- **Normalization:** `normalize_skills_key(["Async", " async ", "OOP"])
  == "async,oop"`. So duplicates and casing don't fragment the bank.
- **Custom ("Other") topic:** UI chip reveals a free-text topic input + a
  free-text skills tag input. On submit, the `InterviewCreate.custom_topic`
  field flows through; questions get persisted under that `topic_name`.
  The topic catalog itself stays curated — `POST /topics/` is the
  recruiter-only path to extend it.

---

## 8. Speech + evaluation pipeline

### Two transcripts per Answer

`Answer.transcript` is the live, low-accuracy Web Speech API transcript
streamed from the candidate's browser. `Answer.whisper_transcript` is the
high-accuracy server-side transcript produced after upload. They are *not
interchangeable* — Gemini evaluation should prefer Whisper when present,
fall back to Web Speech otherwise.

### Background transcription

`POST /candidate/answer` writes the audio file, immediately returns to the
candidate, and queues `_transcribe_audio_background(answer_id, path)` via
`BackgroundTasks`. The background task:

1. Loads the answer row.
2. If file missing → sets `flag_reason = "audio_missing"`.
3. Calls `speech_service.transcribe_audio(path)` inside try/except.
4. On exception → `flag_reason = "transcription_failed"`, logs via
   `logger.exception`.
5. On empty result → `flag_reason = "transcription_empty"` (Whisper saw
   silence / unreadable audio).
6. On success → `whisper_transcript = ...`.

This was a swarm-audit fix: previously the path was `print(...)` + bare
`except`, so failures were invisible.

### Evaluation rubric (current)

`evaluation_service.evaluate_answer(question, transcript, difficulty,
topic)` builds a Gemini prompt with four scalars (each 0–10):

- `correctness` — *Is the technical content accurate?*
- `clarity` — *Is the explanation clear and well-structured?*
- `depth` — *Does the answer show good understanding of the topic?*
- `confidence` — *Does the candidate sound confident and assertive?*

Plus an aggregate `score` (0–100) weighted Technical 60% / Communication
25% / Confidence 15%, plus `feedback`, `strengths`, `areas_for_improvement`.

The prompt asks for JSON; parsing tolerates markdown fences and a
brace-extraction fallback. On failure the candidate router raises HTTP
502 — does **not** persist dummy scores.

### Aggregate

`evaluation_service.calculate_final_score(answers)` averages and returns
`None` for the empty-answers case (callers handle the None). Persisted
onto `Candidate.final_score` and `Candidate.communication_score`.

---

## 9. Proctoring

### Real signals — `useProctoring.ts`

- Tab-switch count (`document.visibilitychange`).
- Clipboard read attempts.
- Blur / focus events.
- Window dimension changes.

These flow into a `tab_switch_count` / `clipboard_count` payload sent to
the backend at completion. `risk_engine.calculate_combined_risk(...)`
maps the counts to `low` / `medium` / `high` and writes
`Candidate.cheating_risk`.

### Stubs — `useFaceDetection`, `useScreenTextDetection`

Both expose `isStub: true` and `console.warn` on mount. They return fixed
placeholder values. **Do not trust their numbers** — they were left in
place during the swarm audit so the contract didn't break, but they need
real face-api.js / Tesseract integration before they mean anything.

### `risk_engine.py`

- Per-request instance, not a module-level singleton (avoids the
  previously-leaking `self.events = []` shared across requests).
- Methods accept `Optional[int]` / `Optional[str]` rather than the old
  bare `= None` annotations.

---

## 10. Known limitations & open problems

### Live open problem — category-aware evaluation

With the dynamic question generator now producing **behavioral**
("Tell me about a time you handled a team conflict"), **system_design**,
and **soft-skill** ("How would you motivate a junior engineer?") questions
— alongside the technical ones — the existing rubric is mis-calibrated:

- *"Correctness — is the technical content accurate?"* is meaningless on a
  behavioral question.
- *"Depth"* measures the wrong thing for soft-skill questions.

Three options on the table (the user paused before picking):

1. **Full version (recommended):** add `category` column to `Question` and
   `QuestionBank`, classify at generation time (Gemini returns
   `[{question, category}]`), branch the eval prompt by category. Map
   per-category metrics back to the existing four scalar columns so no
   `Answer` schema migration is needed; only relabel in the UI.
2. **Prompt-only quick fix:** classify on the fly inside `evaluate_answer`,
   no schema change. Costs an extra small Gemini call per evaluation.
3. **Skills-aware single rubric:** pass `(skills, topic, difficulty)` into
   one universal prompt and let Gemini self-calibrate. Cheapest, weakest
   signal.

This is the most important open question right now. The choice gates how
soon non-technical questions yield trustworthy scores.

### Other security follow-ups

- **JWT in localStorage (recruiter token).** XSS-readable. Documented as
  ISSUE-22 in the swarm audit; flagged in `api.ts` with a comment. Switch
  to httpOnly cookie session needs a backend refactor.
- **`useVoiceVerification` is UI-only.** Recording is just played back; no
  STT match against the gating phrase. Real fix needs a backend STT-verify
  endpoint.
- **Topics router is public for `GET`** — fine, but `POST /topics/` already
  requires recruiter auth.

### UX gaps

- **Auto-submit timer relies on Web Speech API.** Browsers without it
  (Safari, Firefox) never trigger `lastSpeechAt`, so the silence countdown
  doesn't fire. Need either a "submit now" affordance or a typed-answer
  fallback.
- **Sequential `interview_link` UUIDs are fine**, but candidate IDs and
  answer IDs are sequential integers; ownership checks rely on this not
  being a problem. Documented.

### Tech-debt deprecations

- **Pydantic v1-style `class Config: from_attributes = True`** in many
  schemas — emits deprecation warnings in pytest. Migrate to
  `ConfigDict` before Pydantic v3.
- **`datetime.utcnow()`** still appears in `python-jose` (transitive). Our
  own code is on `datetime.now(timezone.utc)`.
- **Bundled-postcss `<8.5.10` XSS** lives inside `node_modules/next/`.
  Upstream issue, no current Next ships a fixed bundle. Attack surface is
  zero in practice — we don't pipe user-controlled CSS through PostCSS.

---

## 11. Roadmap (phases B / C / D)

The DB-backed bank is the prerequisite for everything that follows.

- **Phase B — smart retriever.** Once the bank has volume (~1000+ rows),
  train a sentence-transformer-based retriever (`all-MiniLM-L6-v2`,
  ~80 MB, CPU). Keys: a string built from `(topic_name + difficulty +
  skills)`. Values: embeddings of `question_text`. Cosine top-k replaces
  the current random sample step in `_resolve_questions`. No new Python
  deps yet — they'd go in when this is implemented.
- **Phase C — Gemini as validator, not generator.** Retriever picks top-k
  candidates; Gemini is asked *"Is this question relevant to (topic,
  difficulty, skills)?"* (1-token answer). Mismatches go into a new
  `RetrieverFeedback` table → corrections retrain the retriever. The
  validator path can also score newly-generated questions before they're
  committed to the bank.
- **Phase D — retire generation.** When validator agreement on retriever
  output reaches ~95% over a rolling window, drop the generation Gemini
  call entirely. Validator can stay as a guardrail. The bank
  (`source = "gemini" | "static" | "manual"` and `times_used`) is already
  shaped to feed this.

The category-aware evaluation work (§10) is parallel to this track —
neither depends on the other.

---

## 12. Anchored design decisions (commit → why)

| Commit | What changed | Why |
|---|---|---|
| `4e735bd` "Removed LiveKit" + `dd503e0` "Apply swarm-audit fixes and remove LiveKit" | LiveKit fully excised: service file, voice router, env vars, deps (Python `livekit`, npm `livekit-client`), API method `getVoiceToken`. `Settings.Config.extra="ignore"` added. | Voice flow moved to browser-only Web Speech + MediaRecorder + server Whisper. Saves the LiveKit tier and removes a real-time-infra dependency. |
| `dd503e0` swarm-audit batch | 49 issues across security/reliability/quality. Highlights: SECRET_KEY validator, CORS lockdown, candidate session token, recruiter ownership checks, streaming uploads with extension/MIME/size guards, lifespan replaces `on_event`, lazy Whisper, fence-stripping Gemini, schema indexes + cascades + unique constraints, frontend security headers. New `backend/tests/` (24 cases). | Pre-launch hardening; turned several silent-failure paths into loud-failure paths. |
| `cfe0223` "Fix runtime bugs surfaced by e2e exercise" | `AnswerSubmittedResponse` schema (stops leaking server fs paths), `flag_reason` persistence on background transcription failures, `useSystemCheck` use-before-declare → `useState` lazy initializer. | Found by actually running the candidate flow end-to-end against a fresh DB. |
| `c0a8f10` "Render FastAPI validation errors instead of [object Object]" | `formatApiError(body, status)` flattens 422 detail arrays to readable strings. | Surfaced when password `min_length=8` validator started rejecting short passwords. Generic API-client UX fix. |
| `7598b31` "Bump Next to 16.2.5 and patch transitive deps" | Resolved 5 npm-audit findings — CSRF bypasses, request smuggling, image-cache exhaustion in Next 16.1.6; transient `flatted` / `picomatch` / `brace-expansion`. | Routine security upgrade; kept Next on the same major. |
| `1b9aebb` "Preview canned questions when a topic is selected" | `GET /interviews/sample-questions/{topic_id}` + dashboard preview cards. | Recruiter visibility — they had no way to see what questions a topic produced before save. |
| `65e9f0c` "Stratify question banks by difficulty" | Added easy/medium/hard buckets to the static SAMPLE_QUESTIONS dict; `create_interview` picks the matching bucket; preview takes a difficulty param. | Difficulty was previously evaluation-only and didn't change which questions got asked — surprising. |
| `6b4061d` "Generate interview questions dynamically via Gemini" | `question_generator.py` (Gemini, in-process cache, static fallback). Both call sites moved off retired `gemini-1.5-flash` to `gemini-flash-latest`. | Hardcoded banks felt static. Bonus: `evaluate_answer` had been silently 404'ing on the retired model — same fix unstuck production evaluation. |
| `f1ff018` "DB-backed question bank + skills dimension" (current) | `QuestionBank` table; `Topic.skills` + `Interview.skills`; `services/skills.py` (`GENERAL_SKILLS`, `normalize_skills_key/list`); `_resolve_questions` bank-first; "Other" custom-topic branch in UI; 10 new tests. | Free-tier token economy. The bank seeds itself naturally and gets reused across recruiters; "Regenerate" is the only path that costs tokens after warmup. |

---

## 13. Where to dig next

**For the latest semantics, read in this order:**

1. `backend/app/models/models.py` — current schema is the source of truth.
2. `backend/app/routers/interviews.py` — `_resolve_questions`,
   `_persist_to_bank`, `create_interview`, the two preview endpoints.
3. `backend/app/services/question_generator.py` — pure Gemini call, no
   side effects.
4. `backend/app/routers/candidate.py` — the 13-endpoint hub of the
   candidate flow + recruiter management.
5. `backend/tests/test_question_bank.py` — 10 cases that *describe* the
   bank-vs-Gemini contract. Reading the tests is the fastest way to
   internalize the lookup behavior.
6. `frontend/src/app/recruiter/dashboard/page.tsx` — the create-interview
   form + the per-topic skills/preview cards.
7. `frontend/src/services/api.ts` — every backend call passes through
   here, including the error-formatter.

**Skip / treat as historical:**

- `PHASE1.md` … `PHASE10.md`, `PROJECT_PLAN.md` — outdated. They describe
  intent during early build-out; verify against code.
- README.md's LiveKit references and the older `gemini-1.5-flash` mentions.

**Tests that double as contracts:**

- `test_auth.py` — auth flow + login timing-safety.
- `test_candidate_flow.py` — candidate session token enforcement.
- `test_video_ownership.py` — cross-recruiter isolation.
- `test_uploads.py` — extension / MIME / size limits.
- `test_evaluation_helpers.py` — Gemini fence stripping, empty-answer
  guard, question distribution.
- `test_db_constraints.py` — cascade deletes + unique constraints.
- `test_question_bank.py` — bank lookup + Gemini fallback decision tree.

**Memory artifacts (LLM agent context):**

- `~/.claude/projects/.../memory/livekit_removed.md`
- `~/.claude/projects/.../memory/feedback_auto_commit.md`

Both are referenced by the agent during sessions and shouldn't drift from
ground truth.
