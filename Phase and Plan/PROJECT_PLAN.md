# Plan: AI Interviewer as Defensible Filter

## Context

This is a multi-phase plan to evolve the AI Interviewer from "voice-driven quiz that produces an opaque score" to "low-confidence reject filter that recruiters and lawyers can defend." The product reframe is critical: **this filters out unqualified candidates so HR doesn't waste time on them. It does not decide who to hire.** That framing should drive every implementation choice you make. If you find yourself building something that only makes sense for a hire/no-hire gate, stop and re-read this paragraph.

The research backing these decisions: per-question rubrics (Pathak et al. ICER 2025) raise LLM-grader agreement with humans from ICC ≈ 0.56 to ≈ 0.82. Voice-tone/prosody scoring is now legally radioactive (ACLU v. Intuit/HireVue, March 2025). Cheating detection from voice alone against tools like Cluely is essentially unsolved (Bergmans et al. 2021 found Proctorio caught 0/6 cheaters in a controlled study); vendor claims of 85-98% detection are unverified. Mobley v. Workday establishes vendor liability for AI hiring decisions.

Read `PROJECT_CONTEXT.md` and `CLAUDE.md` first if you haven't. Trust the code over the docs when they disagree (one known disagreement: the doc says `ai_interviewer.db` is checked in, it isn't — `.gitignore` has `*.db`).

## Conventions for this work

- Run `pytest -q` from `backend/` after every meaningful change. The suite is currently 34/34 passing. Fresh installs may pull `httpx 0.28+` which breaks Starlette's `TestClient` — pin `httpx>=0.27,<0.28` in `requirements-dev.txt` if needed.
- No DB migrations exist. Schema changes require deleting `backend/ai_interviewer.db` and restarting. Document this in any commit that touches schema.
- Every new column added to existing tables must default sensibly so existing rows survive without backfill.
- No new Pydantic v1-style `class Config: from_attributes = True`. Use `model_config = ConfigDict(from_attributes=True)`.
- Use `datetime.now(timezone.utc)`, never `datetime.utcnow()`.
- Tests are required for any change that touches `_resolve_questions`, `_persist_to_bank`, `evaluate_answer`, or auth ownership checks.
- Don't add anything that scores delivery (prosody, tone, fluency, speaking rate). Score what was said, not how it was said.
- Don't auto-reject candidates without a recruiter human-in-the-loop confirmation step in the flow.

## Phase 0 — Stop the bleeding (do this first, ~1 week)

These are subtractions and bug fixes. They reduce legal/correctness risk before any new features land.

### 0.1 Remove the `confidence` rubric dimension

The current `evaluation_service.evaluate_answer` prompt asks "Does the candidate sound confident and assertive?" This is delivery scoring. It biases against accented speakers, neurodivergent candidates, and anxious candidates. There is no defensible job-performance correlation. The ACLU v. Intuit/HireVue complaint is built around exactly this kind of scoring.

- In `backend/app/services/evaluation_service.py`: remove `confidence` from the prompt's rubric list and from the rubric weighting. Remove `confidence` and `confidence_score` from the returned dict's authoritative fields. Drop the 60/25/15 weighting; we'll replace this with rubric-anchored scoring in Phase 1, but for now use just `correctness + clarity + depth` averaged.
- In `backend/app/routers/candidate.py`: stop writing `answer.confidence_score` in `evaluate_answer` and `evaluate_candidate`.
- Keep the `Answer.confidence_score` *column* in the model — leave it nullable, stop populating it. Don't migrate; existing rows are fine.
- Search the frontend for any UI that displays "confidence" — remove it from the recruiter report rendering.

### 0.2 Persist proctoring events properly

`save_proctoring_data` currently returns `{persisted: false}` and the `flag_reason` strings `"tab_switch"` and `"clipboard"` that `get_proctoring_report` reads are never set anywhere in the codebase. The whole proctoring path is end-to-end no-op. Fix:

- Add a `ProctoringEvent` table to `backend/app/models/models.py`:
  - `id` int PK
  - `candidate_id` FK to `candidates.id`, ON DELETE CASCADE, indexed
  - `event_type` string (one of: `tab_switch`, `window_blur`, `clipboard_read`, `clipboard_paste`, `focus_loss`)
  - `timestamp` datetime, default `_utcnow`
  - `details` JSON nullable (for future fields)
  - Index on `(candidate_id, event_type)`
- Define a Pydantic request schema for the proctoring endpoint that accepts a list of events.
- In `candidate.py`'s `save_proctoring_data`: accept the events list, validate ownership, write rows. Return `{persisted: true, count: N}`.
- Rewrite `get_proctoring_report` to count events from the new table per `event_type` instead of scanning `Answer.flag_reason`. Keep using `RiskEngine.calculate_combined_risk` for the level computation.
- In `frontend/src/hooks/useProctoring.ts`: when events are collected, POST them to the proctoring endpoint. Batch every 10 events or every 30 seconds, whichever first.
- Add a test in `backend/tests/test_proctoring.py` covering: events get persisted; `get_proctoring_report` reads from `ProctoringEvent` not `Answer.flag_reason`; cross-recruiter ownership check holds.

### 0.3 Reframe the recruiter report as bands, not raw scores

Recruiters see "73/100" today and have to draw their own threshold line. That's not a filter — it's a number generator. Replace the headline with percentile bands within role family.

- In `backend/app/routers/candidate.py`'s `get_candidate_report`: compute the candidate's percentile among all candidates with the same `interview.role` and `interview.difficulty` who have a non-null `final_score`. Bin into `top_30`, `middle`, `bottom_30`. If fewer than 10 candidates exist for that role+difficulty, return `band: "insufficient_data"` and surface this clearly in the response.
- Return both `band` and the raw `final_score` (raw stays for debugging, but the frontend should hide it).
- In `frontend/src/app/recruiter/interview/[id]/candidates/page.tsx`: render the band as the headline. Hide the raw 0-100 number from the headline. Per-question evaluation list and rubric breakdowns stay visible below.

### 0.4 Stop cutting candidates off mid-thought

Six seconds of silence triggers auto-submit. Real interviewers wait longer for thinking pauses. Candidates without Web Speech API support (Safari, Firefox) never trigger `lastSpeechAt` and are stuck.

- In `frontend/src/app/interview/[link]/page.tsx`: bump `AUTO_SUBMIT_SILENCE_MS` from 6000 to 12000.
- Add a visible "Submit answer" button to the interview UI that calls `submitAnswer` directly. The button is the primary path; auto-submit is the fallback.
- The button must be disabled while `submitting` is true to prevent double-submission.

### 0.5 Fix the dead transcription error branch

`speech_service.transcribe_audio` swallows all exceptions internally and returns `""`. This means the `except Exception:` branch in `_transcribe_audio_background` that sets `flag_reason = "transcription_failed"` is unreachable. Real Whisper failures get reclassified as `transcription_empty` (silence). Either let the exception propagate from the service, or drop the dead branch.

- In `backend/app/services/speech_service.py`: in `transcribe_audio`, remove the `try/except Exception` wrapper. Let exceptions propagate. The `print(f"Error transcribing audio: {e}")` line goes too — replace with `logger.exception(...)` if logging is wanted, but the exception must propagate.
- Same change in `transcribe_video` and `transcribe_from_blob`.
- The background task's `except Exception:` branch in `candidate.py` now actually fires on real failures and sets `flag_reason = "transcription_failed"`. Verify by adding a test that monkeypatches `transcribe_audio` to raise, and asserts `Answer.flag_reason == "transcription_failed"`.

### 0.6 Other small hygiene

- `backend/app/services/risk_engine.py`: replace the two `datetime.utcnow()` calls (lines 30 and 100) with `datetime.now(timezone.utc)`.
- Pin `httpx>=0.27,<0.28` in `requirements-dev.txt`.
- Delete `backend/backend/uploads/` (stray directory with two leftover candidate audio files from an earlier directory layout). Add `backend/uploads/` and `backend/backend/` to `.gitignore`.
- The README still references LiveKit and `POST /api/v1/voice/token` and `gemini-1.5-flash`. Update those mentions to match current code.

Run the test suite. Confirm 34/34 still passes plus the new proctoring test (35/35 or more depending on how granularly you wrote tests).

## Phase 1 — Per-question rubric anchoring (~2 weeks)

This is the single biggest scoring quality change. Generic rubrics get ~0.56 ICC with humans; per-question rubrics get ~0.82. Question rubrics are generated alongside the question in the same Gemini call, so generation cost doesn't go up. Evaluation cost goes up ~10-15% per call because the rubric is in the prompt.

### 1.1 Schema changes

- Add `rubric_json: JSON nullable, default None` to `QuestionBank` in `backend/app/models/models.py`.
- Add `rubric_json: JSON nullable, default None` to `Question`. The rubric travels with the question into the interview so candidate-side and evaluation-side don't need to re-fetch from the bank.
- Add to `Answer`:
  - `rubric_score: Float nullable` (0-4 scale)
  - `rubric_justification: Text nullable`
  - `missing_concepts: JSON nullable` (list of strings)
- Keep `correctness`, `clarity`, `depth` columns nullable for back-compat. Stop populating them after this change.

This requires deleting `ai_interviewer.db` and restarting, which is documented as the migration model. Make sure the seed-default-topics path still works after schema delete.

### 1.2 Generator changes

In `backend/app/services/question_generator.py`, rewrite the prompt and parser to produce `[{question, rubric}, ...]` instead of `[question, ...]`. The new prompt should produce:

```json
[
  {
    "question": "Explain how Python's GIL affects multithreaded code.",
    "rubric": {
      "key_concepts": ["GIL serializes bytecode execution", "I/O-bound vs CPU-bound", "multiprocessing as workaround"],
      "anchors": {
        "0": "No answer or completely off-topic",
        "1": "Vague — mentions GIL exists but doesn't explain its effect",
        "2": "Partial — describes the lock but not the I/O-vs-CPU distinction",
        "3": "Specific — explains GIL serializes execution and that I/O-bound code is unaffected",
        "4": "Exemplary — adds concrete tradeoff (multiprocessing, GIL release in C extensions, asyncio for I/O concurrency)"
      }
    }
  }
]
```

The parser must:
- Tolerate the old shape (string-only questions). Treat them as `{question, rubric: None}` for backward compatibility with bank rows generated before this change.
- Tolerate fence-wrapped JSON (existing logic).
- Validate the `rubric` shape before persisting — `key_concepts` must be a non-empty list of strings; `anchors` must have keys "0" through "4" with non-empty string values. If validation fails, treat the rubric as None (don't reject the question itself).

### 1.3 Bank and resolver changes

- `_persist_to_bank` in `backend/app/routers/interviews.py`: accept and write `rubric_json` alongside `question_text`. Existing dedup on `question_text` is unchanged.
- `_resolve_questions`: return `list[tuple[str, dict | None]]` instead of `list[str]`. Update the bank-hit path to read `rubric_json`. Update the generator-fallback path to extract `rubric` from the new generator output. The static fallback in `_static_bank` returns rubric as `None`.
- `create_interview`: write `rubric_json` to each created `Question` row.
- The two preview endpoints (`/sample-questions/{topic_id}` and `/sample-questions/by-name/{topic_name}`): include `rubric` in the per-question response so the dashboard can preview it.

### 1.4 Evaluation changes

In `backend/app/services/evaluation_service.py`:

- Replace the existing prompt with one that takes `(question, rubric, transcript)` and asks for `{rubric_score: 0-4, justification: str, missing_concepts: list[str]}`. If `rubric` is None (legacy question without one), fall back to the old generic prompt — but mark `_legacy: true` in the returned dict so the recruiter UI can flag it as lower-confidence.
- Drop the `evaluate_communication` method entirely. Per-question rubric scores aggregate to a single 0-4 mean; convert that to 0-100 only for sorting/percentile computations, never for display.
- `calculate_final_score`: take `[answer_evaluations]` only (drop the `communication_score` argument). Mean of `rubric_score` × 25 = 0-100 score. Return `None` for empty input.

In `backend/app/routers/candidate.py`:

- `evaluate_answer` and `evaluate_candidate`: pass `answer.question.rubric_json` to `evaluate_answer`. Write `rubric_score`, `rubric_justification`, `missing_concepts` to the `Answer` row. Don't write `correctness`/`clarity`/`depth` anymore.
- `get_candidate_report`: include per-question `rubric_score`, `justification`, and `missing_concepts` in the per-question evaluation list. The recruiter UI will render these as the explanation for each score.

### 1.5 Frontend report changes

In `frontend/src/app/recruiter/interview/[id]/candidates/page.tsx`: render each question's evaluation as `{rubric_score}/4` plus the one-sentence justification plus the missing-concepts list. The percentile band from Phase 0 is the headline.

In the recruiter dashboard preview (`frontend/src/app/recruiter/dashboard/page.tsx`): when previewing sample questions, show a small "rubric" disclosure under each question so the recruiter can review what good/bad answers look like before they save the interview.

### 1.6 Tests

Add `backend/tests/test_rubric.py`:
- Generator returns the new shape; parser tolerates old shape.
- `_resolve_questions` round-trips rubric from bank to caller.
- `evaluate_answer` with a rubric in the prompt returns `rubric_score`.
- `evaluate_answer` with no rubric falls back to the generic prompt and returns `_legacy: true`.
- The `force_refresh` path persists rubrics into the bank.

Run the suite. Verify the new tests pass and existing tests don't regress (some `test_question_bank.py` cases may need updates because `_resolve_questions` now returns tuples).

## Phase 2 — Real cheating signals (~2 weeks)

The honest framing for everything in this phase: these are *soft signals* surfaced to the recruiter as a pattern-of-evidence panel. They never auto-reject. We do not claim percentages. The most informative signal is content-side follow-up logic, which is also the only signal that genuinely defeats Cluely-class tools.

### 2.1 Per-question response latency

Constant-cadence answers regardless of question difficulty are the highest-signal cheating tell that doesn't require special hardware (the cheater pipeline takes a relatively constant 3-5s).

- Add to `Answer`:
  - `started_at: DateTime nullable` — when TTS finishes and the candidate's mic activates
  - `first_word_ms: Integer nullable` — ms from `started_at` to the first non-empty Web Speech result
- Frontend: in `useVoiceInterview.ts`, capture the timestamp when `startAnswer` resolves, and the timestamp of the first `onresult` callback that has a non-empty transcript. Compute `first_word_ms` as the delta. Submit both with the answer FormData.
- Backend: `submit_answer` accepts and persists these fields.
- `get_candidate_report`: include per-answer `first_word_ms`, plus the candidate's within-candidate variance and mean. Surface in the integrity panel section of the report.

### 2.2 Speaker verification across answers

Catches the proxy-interview case (someone else takes the interview). Cannot be defeated by voice-relay tools that play the candidate's own voice.

- Add `voice_embedding: BLOB nullable` to `Answer` (or store as `JSON` of float list, depending on what's simpler given the SQLAlchemy setup).
- In `backend/app/services/`, create `speaker_verification.py`. Use a small open-source speaker encoder — `speechbrain` with `pretrained_models/spkrec-ecapa-voxceleb` is the simplest option (~80MB, EER ~1-2% on clean audio). Lazy-load the model under a lock, same pattern as `speech_service`. Function: `extract_embedding(audio_path: str) -> bytes` and `cosine_distance(a: bytes, b: bytes) -> float`.
- In `_transcribe_audio_background`, after Whisper succeeds, also extract the speaker embedding and store on the answer.
- Add a per-candidate computation in `get_candidate_report`: cosine-distance of each answer's embedding against the *first* answer's embedding. Report mean and max distance. Flag when max > 0.3 (typical ECAPA-TDNN threshold; tune with real data).
- Privacy and consent: in the candidate registration UI, add an explicit checkbox: "I consent to voice analysis for identity verification during this interview. My voice data will be retained for [N] days after the recruiter's decision and then deleted." Make the flow refuse to register without consent. Add `voice_consent_at: DateTime nullable` to `Candidate`.
- Add a daily cleanup job (or document it as a manual cron task) that deletes `voice_embedding` from `Answer` rows older than the retention period.

### 2.3 Vocabulary and structural-marker tracking

Catches the "candidate becomes suspiciously fluent in answer 5" pattern. Cheap.

- Add a small utility module `backend/app/services/transcript_features.py`:
  - `word_count(transcript: str) -> int`
  - `sentence_length_variance(transcript: str) -> float`
  - `structural_marker_count(transcript: str) -> int` — count occurrences of "firstly", "secondly", "in conclusion", numbered list patterns, "to summarize", etc. (case-insensitive).
- Add to `Answer`: `transcript_features: JSON nullable` storing `{word_count, sentence_length_variance, structural_marker_count}`.
- Compute these from `whisper_transcript or transcript` after submission. Persist.
- Surface within-candidate trends in the integrity panel.

### 2.4 Content-side follow-up (the actual anti-cheat)

This is the highest-leverage countermeasure: when a candidate gives a strong (rubric_score >= 3) answer, the AI asks one follow-up that anchors to a specific claim *in the candidate's actual answer*. Cheaters using LLMs struggle here because their LLM has no continuity with the candidate's claimed history.

This violates the "no live conversation" minimalism we agreed on, but it's bounded (one extra question per strong answer, predictable token cost) and it's the only signal that truly defeats Cluely.

- Behind a feature flag (`ENABLE_FOLLOWUP_QUESTIONS`, env var, default false until tested):
- After Whisper transcription completes for an answer, if the (newly persisted) `rubric_score` is None — wait for evaluation. After evaluation, if `rubric_score >= 3`:
  - Make a Gemini call with the question, the transcript, and the rubric. Prompt: "Generate one specific follow-up question that anchors to a concrete claim in the candidate's answer. Do not generate a generic 'tell me more' question. Reference a specific noun or claim from the answer."
  - Persist a new `Question` row with `interview_id` set, `topic_id` from the original question, `question_text` set to the follow-up, `source = "followup"`. Generate a fresh rubric for it via the same call.
  - Frontend: poll for new questions on the same interview after submitting an answer. If a new question appeared, ask it before moving to the next pre-rolled question.
- Cost: one extra Gemini call per strong answer. Only fires on `rubric_score >= 3` (i.e., serious candidates), so it concentrates spend on the candidates who matter.
- Add a soft cap: max one follow-up per original question, max three follow-ups per interview total. Configurable.

### 2.5 Integrity panel in the recruiter UI

A single component on the candidate report page that surfaces:
- Tab/window/clipboard event counts (from Phase 0.2)
- First-word latency: mean, variance (flag if variance is bottom-decile)
- Speaker verification: mean and max cosine distance from first answer (flag if max > 0.3)
- Vocabulary/structural trends per question
- Risk level from `RiskEngine` (kept for back-compat)

This panel is informational. Decision is the recruiter's. Don't surface a single "cheat probability" number — the research on text AI-detection (61% FPR on non-native English writers) shows that any single-number claim is liability waiting to happen.

### 2.6 Tests

Add `backend/tests/test_integrity_signals.py`:
- Latency fields persist correctly
- Speaker embedding extraction round-trips and cosine distance is sensible (test with two clips of the same voice vs. two voices)
- `transcript_features` extracts plausible counts on synthetic inputs
- Follow-up question generation creates a `source="followup"` row and respects the max-followups cap

## Phase 3 — Calibration and bias-audit groundwork (~4 weeks, gated on Phase 0-2 producing data)

This is what turns the score into a filter. Don't start until Phase 1 is producing consistent rubric scores in production.

### 3.1 Recruiter advance/reject feedback

- Add to `Candidate`:
  - `recruiter_decision: String nullable` — values: `'advance'`, `'reject'`, or null
  - `recruiter_decision_at: DateTime nullable`
  - `recruiter_decision_reason: Text nullable`
- New endpoint in `candidate.py`: `POST /candidate/{candidate_id}/decision` with body `{decision: 'advance' | 'reject', reason?: str}`. Recruiter-auth-gated, ownership-checked.
- Frontend candidate report page: two big buttons, "Advance to next round" / "Reject." Optional one-line reason field. Posts to the new endpoint.

### 3.2 Threshold calibration via isotonic regression

- Once the system has ~100 advance/reject labels in a (role, difficulty) bucket, fit an isotonic regression: input = mean `rubric_score` × 25 (so 0-100), output = P(recruiter advances).
- Store the fit per (role, difficulty) bucket in a new table `CalibrationFit(role, difficulty, fit_json, calibrated_at, sample_size)`.
- Refit weekly via a cron task (or a manually-triggered endpoint).
- New filter recommendation field in `get_candidate_report`: `filter_recommendation: 'advance' | 'review' | 'reject'`. Compute as: `P(advance) >= 0.5 → advance; 0.25 <= P < 0.5 → review; P < 0.25 → reject`. If `sample_size < 100`, return `'review'` for everyone (insufficient calibration).
- The recruiter UI shows the recommendation but **never auto-rejects**. The advance/reject buttons are still required.

### 3.3 Shadow mode

For a customer's first 100 candidates per role family, compute the filter recommendation but don't surface it as a recommendation — just log it alongside the recruiter's actual decision. After 100 decisions, compute agreement rate (recommendation matches actual decision). Only after agreement rate > 80% does the recommendation surface in the UI for that role family.

This requires a per-customer-per-role flag stored somewhere — simplest is a `CalibrationStatus(role, difficulty, status, sample_size, agreement_rate)` table that the report endpoint consults.

### 3.4 Bias-audit instrumentation

Even without selling into NYC, instrument selection-rate logging now. Required by NYC LL 144 (effective enforcement July 2023, $500-1500/day penalties), and by EU AI Act high-risk obligations (effective Aug 2026, possibly Dec 2027 if Digital Omnibus passes).

- Add to `Candidate` (all explicit opt-in, candidate-controlled):
  - `demographic_gender: String nullable`
  - `demographic_race_ethnicity: String nullable`
  - `demographic_age_range: String nullable`
- Candidate registration UI: optional self-disclosure section with explicit "this is voluntary and used only for bias auditing" copy.
- Periodic job (or admin endpoint): per (role, difficulty) bucket, compute selection rate (% advanced) per demographic group. Compute four-fifths-rule check: lowest-rate group / highest-rate group >= 0.8.
- Log results to a `BiasAuditResult` table. Surface in an admin-only endpoint `GET /admin/bias-audit`.

### 3.5 Tests

- Calibration fit converges sensibly on synthetic data (e.g., logistic-shaped raw → P)
- Filter recommendation defaults to `'review'` when calibration sample is insufficient
- Bias-audit job correctly identifies a four-fifths violation on synthetic data
- Decision endpoint requires recruiter auth and ownership

## Phase 4 — Question hygiene (opportunistic, not gating anything)

### 4.1 Question rotation

`times_used` already exists on `QuestionBank` and `_resolve_questions` orders by `times_used asc, random()`. Tighten this for the per-recruiter case:

- Add `recruiter_id` to a new `QuestionBankUsage(question_bank_id, recruiter_id, last_used_at)` table.
- When `_resolve_questions` selects from the bank, exclude rows where `(bank_row, recruiter_id, in last 30 days)` exists.
- This prevents one recruiter's full pipeline from being fed to Cluely once a single candidate shares the question set.

### 4.2 Category column on `QuestionBank`

- Add `category: String nullable` (one of `technical`, `behavioral`, `system_design`, `communication`, `other`). Set at generation time via the same Gemini call. Default null for legacy rows.
- Modify the generator prompt to ask for the category alongside the question and rubric.
- The category enables future divergent rubric formats (e.g., STAR-anchored rubrics for behavioral) without schema migration.

### 4.3 Drift detection

- Cron job: per question in `QuestionBank` with `times_used > 20`, compute the mean `rubric_score` of all `Answer` rows linked to `Question` rows with that bank text, in the last 30 days vs. all-time. If the mean shifted by > 1 SD, flag the question in a new `QuestionDrift` table.
- Surface in admin endpoint. Treat as a leading indicator of question-bank leak or question-specific cheat targeting. Don't auto-quarantine — manual review.

## Things explicitly not to build

If you find yourself reaching for any of these, stop. They were eliminated for specific reasons.

- Voice-tone, prosody, fluency, speaking-rate, or affect scoring of any kind. Legal landmine post-ACLU/HireVue.
- Facial expression or emotion recognition. Prohibited under EU AI Act Article 5 in employment contexts.
- AI-text detection on transcripts. 61% FPR on non-native English writers per peer-reviewed evidence; on Whisper transcripts of spoken English this is probably worse.
- Gaze tracking or single-camera face-presence detection. Documented racial and gender disparities in the proctoring literature.
- Screen-text OCR of candidate's screen. Privacy hazard, easily defeated by Cluely's overlay rendering, low-yield.
- Auto-rejection without a recruiter human-in-the-loop confirmation. Mobley v. Workday explicitly attacks this pattern.
- Personality, "culture fit," or HEXACO-style scoring. Disability-discrimination liability vector.
- Marketing claims of cheating-detection accuracy ("we catch 90% of cheaters"). No vendor number in this space is independently verified; making a claim without an independent measurement creates legal exposure for no benefit.
- Any feature whose only purpose is to make the candidate's score *higher confidence* without making it *more defensible*.

## Order of operations

Do Phase 0 in full and ship before starting Phase 1. Phase 0's bug fixes (especially the dead-transcription-error branch and the persisted-proctoring-events) need to be live before any new feature work, or you'll be writing on top of a no-op pipeline.

Phase 1 is where most of the user-visible quality lift comes from. Don't skip rubric anchoring to start cheating-detection work; the order matters because Phase 2's content-side follow-up depends on having rubric scores to gate on.

Phase 3 is gated on having actual labeled outcome data, which requires Phases 0-2 in production with real candidates. Don't try to calibrate against synthetic labels.

Phase 4 is opportunistic — pick up any item when there's spare cycles, none of it blocks anything else.

## What "done" looks like for each phase

- Phase 0 done = no `confidence` scoring, proctoring events actually persist, recruiter sees bands not raw scores, candidates aren't cut off at 6 seconds, transcription failures show up correctly.
- Phase 1 done = every new question has a rubric, every new evaluation produces a rubric-anchored score with justification, recruiter UI shows the rubric and justification per question.
- Phase 2 done = integrity panel in the recruiter UI surfaces latency, speaker-verification, vocabulary signals; consent flow for voice biometrics is in place; follow-up questions feature-flagged on for testing.
- Phase 3 done = recruiter advance/reject loop populating calibration set; isotonic-regression fit per role family; shadow mode for new customers; bias-audit instrumentation logging selection rates per demographic.
- Phase 4 done when picked up = question rotation prevents recruiter-pipeline leakage; categories tagged on new bank rows; drift detection running.

Begin with Phase 0.1 (drop the confidence rubric). It's a single-file change, low risk, high signal. After that ships and tests pass, proceed through 0.2-0.6 in order.