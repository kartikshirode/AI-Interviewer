"""Candidate-facing API.

Authentication model:
- Public endpoints (no token):
  * GET  /candidate/interview/{interview_link}     — look up an interview by link
  * POST /candidate/interview/{interview_id}/register — issues a candidate session token
- Candidate-token endpoints (require Bearer token issued at registration):
  * Everything the candidate needs during the interview (questions, start,
    submit answer, complete).
- Recruiter-token endpoints (require recruiter Bearer token + ownership of
  the candidate's interview):
  * Transcribe-all, evaluate, proctoring report, candidate report.
"""

import logging
import os
import uuid
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_candidate_token
from app.models.models import (
    Answer,
    Candidate,
    Interview,
    ProctoringEvent,
    Question,
    Recruiter,
    Topic,
)
from app.models.schemas import (
    AnswerSubmittedResponse,
    CandidateCreate,
    CandidateRegistrationResponse,
    CandidateResponse,
    ProctoringEventsBatch,
    QuestionResponse,
)
from app.routers.auth import get_current_candidate, get_current_recruiter

# Anchor the upload dir to the backend/ directory so it doesn't depend on CWD.
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_AUDIO_EXTS = {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".oga"}
ALLOWED_VIDEO_EXTS = {".webm", ".mp4", ".mkv", ".mov", ".avi"}
ALLOWED_AUDIO_MIME_PREFIXES = ("audio/",)
ALLOWED_VIDEO_MIME_PREFIXES = ("video/",)
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB

router = APIRouter(prefix="/candidate", tags=["Candidate Interview"])


def _ensure_owns_candidate(db: Session, recruiter: Recruiter, candidate: Candidate) -> None:
    interview = (
        db.query(Interview)
        .filter(
            Interview.id == candidate.interview_id,
            Interview.recruiter_id == recruiter.id,
        )
        .first()
    )
    if not interview:
        raise HTTPException(status_code=404, detail="Candidate not found")


async def _stream_upload_to_disk(
    upload: UploadFile,
    allowed_exts: set,
    allowed_mime_prefixes: tuple,
    max_size: int = settings.MAX_UPLOAD_SIZE,
) -> str:
    """Stream `upload` to UPLOAD_DIR in chunks, validating extension, MIME
    type, and size. Returns the absolute on-disk path."""
    file_ext = os.path.splitext(upload.filename or "")[1].lower() or ".bin"
    if file_ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension: {file_ext}",
        )

    content_type = (upload.content_type or "").lower()
    if content_type and not any(
        content_type.startswith(p) for p in allowed_mime_prefixes
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content-type: {content_type}",
        )

    file_name = f"{uuid.uuid4()}{file_ext}"
    out_path = UPLOAD_DIR / file_name
    written = 0
    try:
        with open(out_path, "wb") as f:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_size:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds maximum size of {max_size} bytes",
                    )
                f.write(chunk)
    except HTTPException:
        # Clean partial file on validation error
        try:
            if out_path.exists():
                out_path.unlink()
        except OSError:
            pass
        raise

    return str(out_path)


# ---------------------------------------------------------------------------
# Public — interview lookup
# ---------------------------------------------------------------------------

@router.get("/interview/{interview_link}")
def get_interview_by_link(interview_link: str, db: Session = Depends(get_db)):
    interview = (
        db.query(Interview).filter(Interview.interview_link == interview_link).first()
    )
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    return {
        "id": interview.id,
        "role": interview.role,
        "difficulty": interview.difficulty,
        "num_questions": interview.num_questions,
        "status": interview.status,
        # Phase 2.2: tell the candidate's browser whether the operator
        # has enabled voice biometrics so the registration form can show
        # the consent checkbox conditionally. The backend still enforces
        # consent on registration when the flag is on — this is just UX.
        "requires_voice_consent": settings.ENABLE_SPEAKER_VERIFICATION,
        "voice_data_retention_days": settings.SPEAKER_DATA_RETENTION_DAYS,
    }


# ---------------------------------------------------------------------------
# Public — registration (issues candidate session token)
# ---------------------------------------------------------------------------

@router.post(
    "/interview/{interview_id}/register",
    response_model=CandidateRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_candidate(
    interview_id: int, candidate: CandidateCreate, db: Session = Depends(get_db)
):
    from datetime import datetime, timezone

    interview = db.query(Interview).filter(Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    # Phase 2.2: when speaker verification is on, registration must
    # carry an explicit `voice_consent: true` — voice biometrics need
    # informed consent. We record the consent timestamp; absence of
    # consent (or consent=false) refuses the registration with 400.
    voice_consent_at = None
    if settings.ENABLE_SPEAKER_VERIFICATION:
        if not candidate.voice_consent:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Voice analysis consent is required to take this "
                    "interview. Your voice will be analyzed for identity "
                    "verification and the embedding deleted after "
                    f"{settings.SPEAKER_DATA_RETENTION_DAYS} days."
                ),
            )
        voice_consent_at = datetime.now(timezone.utc)

    # Re-use existing candidate row for the same (interview, email) so retrying
    # registration doesn't break the unique constraint.
    db_candidate = (
        db.query(Candidate)
        .filter(
            Candidate.interview_id == interview_id,
            Candidate.email == candidate.email,
        )
        .first()
    )
    if db_candidate:
        # Update name in case the candidate corrected a typo.
        db_candidate.name = candidate.name
        if voice_consent_at is not None and db_candidate.voice_consent_at is None:
            db_candidate.voice_consent_at = voice_consent_at
        db.commit()
        db.refresh(db_candidate)
    else:
        db_candidate = Candidate(
            interview_id=interview_id,
            name=candidate.name,
            email=candidate.email,
            status="registered",
            voice_consent_at=voice_consent_at,
        )
        db.add(db_candidate)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            db_candidate = (
                db.query(Candidate)
                .filter(
                    Candidate.interview_id == interview_id,
                    Candidate.email == candidate.email,
                )
                .first()
            )
            if not db_candidate:
                raise HTTPException(status_code=500, detail="Registration failed")
        else:
            db.refresh(db_candidate)

    token = create_candidate_token(db_candidate.id, interview_id)

    payload = CandidateRegistrationResponse(
        id=db_candidate.id,
        interview_id=db_candidate.interview_id,
        name=db_candidate.name,
        email=db_candidate.email,
        status=db_candidate.status,
        final_score=db_candidate.final_score,
        communication_score=db_candidate.communication_score,
        cheating_risk=db_candidate.cheating_risk,
        session_token=token,
    )
    return payload


# ---------------------------------------------------------------------------
# Candidate-authenticated endpoints
# ---------------------------------------------------------------------------

@router.get("/interview/{interview_id}/questions", response_model=List[QuestionResponse])
def get_interview_questions_for_candidate(
    interview_id: int,
    db: Session = Depends(get_db),
    candidate: Candidate = Depends(get_current_candidate),
):
    if candidate.interview_id != interview_id:
        raise HTTPException(status_code=403, detail="Token/interview mismatch")

    interview = db.query(Interview).filter(Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    return db.query(Question).filter(Question.interview_id == interview_id).all()


@router.post("/interview/{interview_id}/start")
def start_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    candidate: Candidate = Depends(get_current_candidate),
):
    if candidate.interview_id != interview_id:
        raise HTTPException(status_code=403, detail="Token/interview mismatch")

    candidate.status = "in_progress"
    db.commit()
    return {"status": "started", "candidate_id": candidate.id}


def _maybe_generate_followup(db: Session, answer: Answer) -> None:
    """Phase 2.4: feature-flagged content-side follow-up.

    Triggered when a strong answer (`rubric_score >= settings.FOLLOWUP_THRESHOLD`)
    has just been evaluated. We ask Gemini for a single follow-up
    question anchored to a specific claim in the transcript and
    persist it as a new `Question` row with `source="followup"` and
    `parent_question_id` set. Caps:
      - max one follow-up per original question
      - max settings.MAX_FOLLOWUPS_PER_INTERVIEW per interview
    Soft-fails: any error path leaves the interview unchanged.
    """
    from app.core.config import settings as _settings

    if not _settings.ENABLE_FOLLOWUP_QUESTIONS:
        return
    if answer.rubric_score is None or answer.rubric_score < _settings.FOLLOWUP_THRESHOLD:
        return

    original = (
        db.query(Question).filter(Question.id == answer.question_id).first()
    )
    if original is None or original.source == "followup":
        # Don't generate follow-ups of follow-ups.
        return

    # Cap 1: one follow-up per original question.
    already_followed = (
        db.query(Question)
        .filter(Question.parent_question_id == original.id)
        .first()
    )
    if already_followed is not None:
        return

    # Cap 2: max-per-interview.
    interview_followup_count = (
        db.query(Question)
        .filter(
            Question.interview_id == original.interview_id,
            Question.source == "followup",
        )
        .count()
    )
    if interview_followup_count >= _settings.MAX_FOLLOWUPS_PER_INTERVIEW:
        return

    transcript = answer.whisper_transcript or answer.transcript or ""
    if not transcript.strip():
        return

    candidate = (
        db.query(Candidate).filter(Candidate.id == answer.candidate_id).first()
    )
    interview = (
        db.query(Interview).filter(Interview.id == candidate.interview_id).first()
        if candidate
        else None
    )
    difficulty = interview.difficulty if interview else "medium"
    topic_name: Optional[str] = None
    if original.topic_id:
        t = db.query(Topic).filter(Topic.id == original.topic_id).first()
        topic_name = t.name if t else None

    from app.services.question_generator import QuestionGenerator
    from app.routers.interviews import _get_generator

    pair = _get_generator().generate_followup(
        question=original.question_text,
        transcript=transcript,
        rubric=original.rubric_json,
        topic=topic_name,
        difficulty=difficulty,
    )
    if pair is None:
        return

    text, rubric = pair
    db.add(
        Question(
            interview_id=original.interview_id,
            topic_id=original.topic_id,
            question_text=text,
            rubric_json=rubric,
            source="followup",
            parent_question_id=original.id,
        )
    )
    db.commit()


def _transcribe_audio_background(answer_id: int, audio_path: str):
    """Background task: run Whisper on recorded audio and update the answer.

    Failures are logged and persisted onto `Answer.flag_reason` so the
    recruiter sees that transcription couldn't run, instead of silently
    leaving `whisper_transcript = NULL` and pretending nothing happened.

    Phase 2.4: when ENABLE_FOLLOWUP_QUESTIONS is set, this task ALSO
    auto-evaluates the answer against the question's rubric and, on a
    strong score, generates a follow-up question. The auto-eval path
    runs only when the flag is on — recruiter-triggered evaluation is
    still the primary scoring path otherwise.
    """
    from app.core.database import SessionLocal
    from app.services.speech_service import speech_service

    db = SessionLocal()
    try:
        answer = db.query(Answer).filter(Answer.id == answer_id).first()
        if not answer:
            logger.warning("Background transcription: answer %s not found", answer_id)
            return
        if not os.path.exists(audio_path):
            logger.warning(
                "Background transcription: audio file missing for answer %s at %s",
                answer_id,
                audio_path,
            )
            answer.flag_reason = "audio_missing"
            db.commit()
            return
        try:
            transcript = speech_service.transcribe_audio(audio_path)
        except Exception:
            logger.exception(
                "Background transcription failed for answer %s", answer_id
            )
            answer.flag_reason = "transcription_failed"
            db.commit()
            return
        if transcript:
            answer.whisper_transcript = transcript
        else:
            # Whisper returned empty — likely silence or unreadable audio.
            answer.flag_reason = "transcription_empty"
        db.commit()

        # Phase 2.2: voice embedding extraction. Off by default; only
        # runs when the operator opted in AND the candidate consented.
        # Soft-fails on every error path so this is never load-bearing.
        try:
            from app.core.config import settings as _vk_settings

            if _vk_settings.ENABLE_SPEAKER_VERIFICATION:
                cand_check = (
                    db.query(Candidate)
                    .filter(Candidate.id == answer.candidate_id)
                    .first()
                )
                if cand_check is not None and cand_check.voice_consent_at is not None:
                    from app.services import speaker_verification

                    embedding = speaker_verification.extract_embedding(audio_path)
                    if embedding is not None:
                        answer.voice_embedding = embedding
                        db.commit()
        except Exception:
            logger.exception(
                "Speaker embedding extraction failed for answer %s", answer_id
            )

        # Phase 2.4 auto-eval + follow-up. Behind the feature flag so
        # the existing recruiter-triggered evaluation path stays the
        # default. Any failure here is non-fatal — the transcript is
        # already persisted.
        from app.core.config import settings as _settings

        if _settings.ENABLE_FOLLOWUP_QUESTIONS and answer.whisper_transcript:
            try:
                from app.services.evaluation_service import evaluation_service

                question = (
                    db.query(Question).filter(Question.id == answer.question_id).first()
                )
                if question is not None:
                    candidate = (
                        db.query(Candidate)
                        .filter(Candidate.id == answer.candidate_id)
                        .first()
                    )
                    interview = (
                        db.query(Interview)
                        .filter(Interview.id == candidate.interview_id)
                        .first()
                        if candidate
                        else None
                    )
                    topic_name: Optional[str] = None
                    if question.topic_id:
                        t = (
                            db.query(Topic)
                            .filter(Topic.id == question.topic_id)
                            .first()
                        )
                        topic_name = t.name if t else None
                    evaluation = evaluation_service.evaluate_answer(
                        question=question.question_text,
                        transcript=answer.whisper_transcript,
                        difficulty=interview.difficulty if interview else "medium",
                        topic=topic_name,
                        rubric=question.rubric_json,
                    )
                    if evaluation.get("_ok"):
                        answer.rubric_score = evaluation.get("rubric_score")
                        answer.rubric_justification = (
                            evaluation.get("justification") or None
                        )
                        answer.missing_concepts = (
                            evaluation.get("missing_concepts") or None
                        )
                        if evaluation.get("_legacy"):
                            answer.correctness = evaluation.get("correctness")
                            answer.clarity = evaluation.get("clarity")
                            answer.depth = evaluation.get("depth")
                        db.commit()
                        _maybe_generate_followup(db, answer)
            except Exception:
                logger.exception(
                    "Phase 2.4 auto-eval / follow-up failed for answer %s",
                    answer_id,
                )
    except Exception:
        logger.exception(
            "Unexpected error in background transcription for answer %s", answer_id
        )
    finally:
        db.close()


@router.post("/answer", response_model=AnswerSubmittedResponse)
async def submit_answer(
    background_tasks: BackgroundTasks,
    candidate_id: int = Form(...),
    question_id: int = Form(...),
    transcript: Optional[str] = Form(None),
    # Phase 2.1: epoch-ms when the candidate's mic actually opened. Optional
    # because older candidate clients won't send it; we trust the client
    # since this is just a soft signal in the integrity panel.
    started_at_ms: Optional[int] = Form(None),
    # Phase 2.1: ms from `started_at_ms` to the first non-empty transcript
    # token. Constant cadence regardless of difficulty is the highest-
    # signal "did this come from a tool" tell.
    first_word_ms: Optional[int] = Form(None),
    audio: Optional[UploadFile] = File(None),
    video: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    candidate: Candidate = Depends(get_current_candidate),
):
    from datetime import datetime, timezone
    from app.services.transcript_features import extract_features

    if candidate.id != candidate_id:
        raise HTTPException(status_code=403, detail="Token/candidate mismatch")

    # Make sure the question belongs to the candidate's interview to prevent
    # cross-interview answer poisoning.
    question = (
        db.query(Question)
        .filter(
            Question.id == question_id,
            Question.interview_id == candidate.interview_id,
        )
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    audio_path: Optional[str] = None
    video_path: Optional[str] = None

    if audio:
        audio_path = await _stream_upload_to_disk(
            audio, ALLOWED_AUDIO_EXTS, ALLOWED_AUDIO_MIME_PREFIXES
        )

    if video:
        video_path = await _stream_upload_to_disk(
            video, ALLOWED_VIDEO_EXTS, ALLOWED_VIDEO_MIME_PREFIXES
        )

    # Phase 2.1 / 2.3: compute integrity-panel signals up front so they
    # land on both the new-row and the update-existing paths below.
    started_at_dt = (
        datetime.fromtimestamp(started_at_ms / 1000.0, tz=timezone.utc)
        if started_at_ms is not None
        else None
    )
    features = extract_features(transcript)

    existing_answer = (
        db.query(Answer)
        .filter(
            Answer.candidate_id == candidate_id,
            Answer.question_id == question_id,
        )
        .first()
    )

    if existing_answer:
        existing_answer.transcript = transcript
        if audio_path:
            existing_answer.audio_path = audio_path
        if video_path:
            existing_answer.video_path = video_path
        if started_at_dt is not None:
            existing_answer.started_at = started_at_dt
        if first_word_ms is not None:
            existing_answer.first_word_ms = first_word_ms
        existing_answer.transcript_features = features
        db.commit()
        db.refresh(existing_answer)
        if audio_path:
            background_tasks.add_task(
                _transcribe_audio_background, existing_answer.id, audio_path
            )
        return existing_answer

    answer = Answer(
        candidate_id=candidate_id,
        question_id=question_id,
        transcript=transcript,
        audio_path=audio_path,
        video_path=video_path,
        started_at=started_at_dt,
        first_word_ms=first_word_ms,
        transcript_features=features,
    )
    db.add(answer)
    try:
        db.commit()
    except IntegrityError:
        # Another concurrent submit raced us. Fall back to updating the
        # existing row.
        db.rollback()
        existing_answer = (
            db.query(Answer)
            .filter(
                Answer.candidate_id == candidate_id,
                Answer.question_id == question_id,
            )
            .first()
        )
        if not existing_answer:
            raise HTTPException(status_code=500, detail="Failed to record answer")
        existing_answer.transcript = transcript
        if audio_path:
            existing_answer.audio_path = audio_path
        if video_path:
            existing_answer.video_path = video_path
        if started_at_dt is not None:
            existing_answer.started_at = started_at_dt
        if first_word_ms is not None:
            existing_answer.first_word_ms = first_word_ms
        existing_answer.transcript_features = features
        db.commit()
        db.refresh(existing_answer)
        if audio_path:
            background_tasks.add_task(
                _transcribe_audio_background, existing_answer.id, audio_path
            )
        return existing_answer

    db.refresh(answer)
    if audio_path:
        background_tasks.add_task(_transcribe_audio_background, answer.id, audio_path)
    return answer


@router.post("/interview/{interview_id}/complete")
def complete_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    candidate: Candidate = Depends(get_current_candidate),
):
    if candidate.interview_id != interview_id:
        raise HTTPException(status_code=403, detail="Token/interview mismatch")

    candidate.status = "completed"
    db.commit()
    return {"status": "completed", "candidate_id": candidate.id}


# ---------------------------------------------------------------------------
# Recruiter-authenticated endpoints
# ---------------------------------------------------------------------------

@router.post("/answer/{answer_id}/transcribe")
def transcribe_answer(
    answer_id: int,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    """Transcribe audio/video for an answer using Whisper."""
    from app.services.speech_service import speech_service

    answer = db.query(Answer).filter(Answer.id == answer_id).first()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    candidate = db.query(Candidate).filter(Candidate.id == answer.candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Answer not found")
    _ensure_owns_candidate(db, recruiter, candidate)

    file_to_transcribe: Optional[str] = None
    if answer.audio_path and os.path.exists(answer.audio_path):
        file_to_transcribe = answer.audio_path
    elif answer.video_path and os.path.exists(answer.video_path):
        file_to_transcribe = answer.video_path

    if not file_to_transcribe:
        return {
            "transcript": answer.whisper_transcript or answer.transcript or "",
            "message": "No audio/video file to transcribe",
        }

    try:
        if file_to_transcribe.lower().endswith((".mp4", ".mkv", ".avi", ".mov")):
            transcript = speech_service.transcribe_video(file_to_transcribe)
        else:
            transcript = speech_service.transcribe_audio(file_to_transcribe)
    except Exception as e:
        # Surface failures via HTTP error (ISSUE-14).
        raise HTTPException(status_code=502, detail=f"Transcription failed: {e}")

    answer.whisper_transcript = transcript
    db.commit()
    return {"transcript": transcript, "status": "success"}


@router.post("/candidate/{candidate_id}/transcribe-all")
def transcribe_all_answers(
    candidate_id: int,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    """Transcribe all answers for a candidate using Whisper.

    Commits once at the end. Returns 207-style payload distinguishing
    succeeded vs. failed answers (ISSUE-29)."""
    from fastapi.responses import JSONResponse
    from app.services.speech_service import speech_service

    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_owns_candidate(db, recruiter, candidate)

    answers = db.query(Answer).filter(Answer.candidate_id == candidate_id).all()
    results = []
    any_failed = False

    for answer in answers:
        file_to_transcribe: Optional[str] = None
        if answer.audio_path and os.path.exists(answer.audio_path):
            file_to_transcribe = answer.audio_path
        elif answer.video_path and os.path.exists(answer.video_path):
            file_to_transcribe = answer.video_path

        if not file_to_transcribe:
            continue

        try:
            if file_to_transcribe.lower().endswith((".mp4", ".mkv", ".avi", ".mov")):
                transcript = speech_service.transcribe_video(file_to_transcribe)
            else:
                transcript = speech_service.transcribe_audio(file_to_transcribe)
            answer.whisper_transcript = transcript
            results.append(
                {"answer_id": answer.id, "transcript": transcript, "status": "success"}
            )
        except Exception as e:
            any_failed = True
            results.append(
                {"answer_id": answer.id, "error": str(e), "status": "failed"}
            )

    # Single commit at the end; rollback on commit failure.
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB commit failed: {e}")

    payload = {"results": results}
    if any_failed:
        # 207 Multi-Status: partial success
        return JSONResponse(status_code=207, content=payload)
    return payload


@router.post("/answer/{answer_id}/evaluate")
def evaluate_answer(
    answer_id: int,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    """Evaluate a single answer."""
    from app.services.evaluation_service import evaluation_service

    answer = db.query(Answer).filter(Answer.id == answer_id).first()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    candidate = db.query(Candidate).filter(Candidate.id == answer.candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Answer not found")
    _ensure_owns_candidate(db, recruiter, candidate)

    transcript = answer.whisper_transcript or answer.transcript
    if not transcript:
        raise HTTPException(
            status_code=400, detail="No transcript available for evaluation"
        )

    question = db.query(Question).filter(Question.id == answer.question_id).first()
    topic = None
    if question and question.topic_id:
        topic_obj = db.query(Topic).filter(Topic.id == question.topic_id).first()
        topic = topic_obj.name if topic_obj else None

    interview = db.query(Interview).filter(Interview.id == candidate.interview_id).first()
    difficulty = interview.difficulty if interview else "medium"

    evaluation = evaluation_service.evaluate_answer(
        question=question.question_text if question else "",
        transcript=transcript,
        difficulty=difficulty,
        topic=topic,
        rubric=question.rubric_json if question else None,
    )

    if not evaluation.get("_ok", False):
        # Don't persist a dummy evaluation; bubble the error.
        raise HTTPException(
            status_code=502,
            detail=f"Evaluation failed: {evaluation.get('_error', 'unknown error')}",
        )

    # Phase 1: persist the rubric-anchored fields. The legacy
    # correctness/clarity/depth columns stay nullable for back-compat
    # but only get populated when the legacy prompt path runs (i.e.
    # questions without a rubric).
    answer.rubric_score = evaluation.get("rubric_score")
    answer.rubric_justification = evaluation.get("justification") or None
    answer.missing_concepts = evaluation.get("missing_concepts") or None
    if evaluation.get("_legacy"):
        answer.correctness = evaluation.get("correctness")
        answer.clarity = evaluation.get("clarity")
        answer.depth = evaluation.get("depth")
    answer.feedback = evaluation.get("justification", "") or evaluation.get("feedback", "")
    db.commit()

    return evaluation


@router.post("/candidate/{candidate_id}/evaluate")
def evaluate_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    """Evaluate all answers for a candidate and calculate final score."""
    from app.services.evaluation_service import evaluation_service

    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_owns_candidate(db, recruiter, candidate)

    # Eager-load related question + topic to avoid the N+1 in the loop below
    # (ISSUE-15/16).
    answers = (
        db.query(Answer)
        .options(joinedload(Answer.question).joinedload(Question.topic))
        .filter(Answer.candidate_id == candidate_id)
        .all()
    )

    if not answers:
        raise HTTPException(status_code=400, detail="No answers to evaluate")

    interview = (
        db.query(Interview).filter(Interview.id == candidate.interview_id).first()
    )
    difficulty = interview.difficulty if interview else "medium"

    answer_evaluations = []
    for answer in answers:
        transcript = answer.whisper_transcript or answer.transcript
        if not transcript:
            continue

        question = answer.question
        topic = question.topic.name if question and question.topic else None

        evaluation = evaluation_service.evaluate_answer(
            question=question.question_text if question else "",
            transcript=transcript,
            difficulty=difficulty,
            topic=topic,
            rubric=question.rubric_json if question else None,
        )

        if not evaluation.get("_ok", False):
            # Skip this answer's persisted score on failure rather than
            # poisoning the DB with dummies.
            continue

        answer.rubric_score = evaluation.get("rubric_score")
        answer.rubric_justification = evaluation.get("justification") or None
        answer.missing_concepts = evaluation.get("missing_concepts") or None
        if evaluation.get("_legacy"):
            answer.correctness = evaluation.get("correctness")
            answer.clarity = evaluation.get("clarity")
            answer.depth = evaluation.get("depth")
        answer.feedback = (
            evaluation.get("justification", "") or evaluation.get("feedback", "")
        )
        answer_evaluations.append(evaluation)

    final_scores = evaluation_service.calculate_final_score(answer_evaluations)

    if final_scores is None:
        db.commit()
        raise HTTPException(
            status_code=502,
            detail="No answers could be evaluated successfully",
        )

    candidate.final_score = final_scores["final_score"]
    db.commit()

    return {
        "final_score": final_scores["final_score"],
        "technical_score": final_scores["technical_score"],
        "answer_evaluations": answer_evaluations,
    }


@router.post("/candidate/{candidate_id}/proctoring")
def save_proctoring_data(
    candidate_id: int,
    body: ProctoringEventsBatch,
    db: Session = Depends(get_db),
    candidate: Candidate = Depends(get_current_candidate),
):
    """Persist proctoring events posted by the candidate's browser.

    Authenticated via the candidate session token (events are emitted
    during the interview, before the recruiter ever sees the candidate's
    record). The token claim must match the path parameter.

    Server-side `ProctoringEvent.timestamp` is the receive-time, not the
    client-supplied one — we don't trust client clocks for ordering.
    Lifecycle events like `monitoring_started`/`monitoring_stopped` are
    silently dropped: they're UI bookkeeping, not signals.
    """
    if candidate.id != candidate_id:
        raise HTTPException(status_code=403, detail="Token/candidate mismatch")

    LIFECYCLE_TYPES = {"monitoring_started", "monitoring_stopped"}

    persisted = 0
    for event in body.events:
        if event.event_type in LIFECYCLE_TYPES:
            continue
        db.add(
            ProctoringEvent(
                candidate_id=candidate_id,
                event_type=event.event_type,
                details=event.details,
            )
        )
        persisted += 1
    db.commit()

    return {
        "status": "received",
        "candidate_id": candidate_id,
        "persisted": True,
        "count": persisted,
    }


@router.post("/candidate/{candidate_id}/proctoring/report")
def get_proctoring_report(
    candidate_id: int,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    """Compute the proctoring risk report from persisted events.

    Reads from `proctoring_events` (populated by the candidate's browser
    via the POST endpoint above). The previous implementation scanned
    `Answer.flag_reason` for strings that were never written anywhere —
    every report came back "low risk" regardless of what happened.
    """
    from app.services.risk_engine import RiskEngine

    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_owns_candidate(db, recruiter, candidate)

    rows = (
        db.query(ProctoringEvent.event_type, func.count(ProctoringEvent.id))
        .filter(ProctoringEvent.candidate_id == candidate_id)
        .group_by(ProctoringEvent.event_type)
        .all()
    )
    counts: dict[str, int] = {event_type: count for event_type, count in rows}

    # Map the hook's emitted vocabulary onto the RiskEngine's count
    # parameters. Anything else still contributes via the engine's own
    # weighting if we add it later.
    risk_result = RiskEngine.calculate_combined_risk(
        tab_switches=counts.get("tab_switch", 0) + counts.get("window_blur", 0) + counts.get("new_tab", 0),
        clipboard_copies=counts.get("clipboard_copy", 0) + counts.get("keyboard_copy", 0),
        clipboard_pastes=counts.get("clipboard_paste", 0) + counts.get("keyboard_paste", 0),
    )

    candidate.cheating_risk = risk_result["risk_level"]
    db.commit()

    # Surface the raw per-type counts so the recruiter UI can render them
    # alongside the engine's level. Decision is the recruiter's; we don't
    # offer a single "cheat probability" number.
    return {**risk_result, "event_counts": counts}


@router.get("/candidate/{candidate_id}/report")
def get_candidate_report(
    candidate_id: int,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    """Generate a comprehensive candidate report."""
    from app.services.evaluation_service import evaluation_service

    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_owns_candidate(db, recruiter, candidate)

    interview = (
        db.query(Interview).filter(Interview.id == candidate.interview_id).first()
    )

    # Eager-load question+topic to kill the N+1 (ISSUE-15/16).
    answers = (
        db.query(Answer)
        .options(joinedload(Answer.question).joinedload(Question.topic))
        .filter(Answer.candidate_id == candidate_id)
        .all()
    )

    question_evaluations = []
    topic_scores: dict = {}
    answer_eval_dicts = []

    for answer in answers:
        question = answer.question
        topic = question.topic.name if question and question.topic else None

        # Phase 1: a per-answer rubric_score is the primary signal. For
        # legacy answers without one we fall back to the mean of the
        # 0-10 trio scaled to 0-4 so the report can still display a
        # number.
        rubric_score = answer.rubric_score
        if rubric_score is None and answer.correctness is not None:
            rubric_score = round(
                (
                    float(answer.correctness or 5)
                    + float(answer.clarity or 5)
                    + float(answer.depth or 5)
                ) / 3 / 2.5,
                2,
            )

        question_evaluations.append(
            {
                "question_id": question.id if question else None,
                "question_text": question.question_text if question else "",
                "rubric": question.rubric_json if question else None,
                "topic": topic,
                "transcript": answer.transcript,
                "video_path": answer.video_path,
                # Phase 1 surface
                "rubric_score": rubric_score,
                "rubric_justification": answer.rubric_justification,
                "missing_concepts": answer.missing_concepts or [],
                "is_legacy_evaluation": answer.rubric_score is None
                and answer.correctness is not None,
                # Legacy debugging fields — kept for old answers
                "correctness": answer.correctness,
                "clarity": answer.clarity,
                "depth": answer.depth,
                # Phase 2.1 / 2.3 per-answer integrity signals
                "first_word_ms": answer.first_word_ms,
                "transcript_features": answer.transcript_features,
                "is_flagged": answer.is_flagged,
                "flag_reason": answer.flag_reason,
            }
        )

        if topic and rubric_score is not None:
            bucket = topic_scores.setdefault(topic, {"total": 0.0, "count": 0})
            bucket["total"] += rubric_score
            bucket["count"] += 1

        if rubric_score is not None:
            answer_eval_dicts.append({"rubric_score": rubric_score})

    topic_averages = {
        t: round(d["total"] / d["count"], 2) if d["count"] > 0 else 0
        for t, d in topic_scores.items()
    }

    # Phase 1: aggregator now consumes rubric_score directly.
    aggregated = evaluation_service.calculate_final_score(answer_eval_dicts)
    technical_score = aggregated["technical_score"] if aggregated else None

    # Phase 0.3: percentile band against the (role, difficulty) cohort.
    # The cohort intentionally includes this candidate so a single-row
    # cohort still produces a defensible 50%-percentile placement (which
    # then maps to `insufficient_data` because n < 10).
    cohort_scores: list[float] = []
    if interview is not None:
        cohort_scores = [
            row[0]
            for row in db.query(Candidate.final_score)
            .join(Interview, Candidate.interview_id == Interview.id)
            .filter(
                Interview.role == interview.role,
                Interview.difficulty == interview.difficulty,
                Candidate.final_score.isnot(None),
            )
            .all()
        ]
    from app.services.evaluation_service import compute_band

    banding = compute_band(candidate.final_score, cohort_scores)

    # Phase 2.5: integrity panel. A pattern-of-evidence block, never a
    # single "cheat probability" number. The recruiter is the decision
    # maker; we surface signals.
    proctoring_counts: dict[str, int] = {}
    for event_type, cnt in (
        db.query(ProctoringEvent.event_type, func.count(ProctoringEvent.id))
        .filter(ProctoringEvent.candidate_id == candidate_id)
        .group_by(ProctoringEvent.event_type)
        .all()
    ):
        proctoring_counts[event_type] = cnt

    latencies_ms = [a.first_word_ms for a in answers if a.first_word_ms is not None]
    feature_blobs = [
        a.transcript_features for a in answers if a.transcript_features
    ]

    def _mean(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 2) if xs else None

    def _variance(xs: list[float]) -> float | None:
        if len(xs) < 2:
            return None
        m = sum(xs) / len(xs)
        return round(sum((x - m) ** 2 for x in xs) / len(xs), 2)

    # Phase 2.2: speaker-verification block. We compare every embedded
    # answer against the FIRST embedded answer's vector; the first
    # answer is the reference, so its distance is 0 by definition.
    # `flagged` = max distance > settings threshold; surfaced as a
    # signal, never as an auto-reject.
    from app.services.speaker_verification import cosine_distance

    embedded_answers = [a for a in answers if a.voice_embedding]
    speaker_block: dict[str, Any] = {
        "enabled": settings.ENABLE_SPEAKER_VERIFICATION,
        "consent_recorded": candidate.voice_consent_at is not None,
        "answer_count": len(embedded_answers),
    }
    if len(embedded_answers) >= 2:
        reference = embedded_answers[0].voice_embedding
        distances: list[float] = []
        for a in embedded_answers[1:]:
            d = cosine_distance(reference, a.voice_embedding)
            if d is not None:
                distances.append(d)
        if distances:
            max_d = max(distances)
            speaker_block.update(
                {
                    "mean_distance": round(sum(distances) / len(distances), 4),
                    "max_distance": round(max_d, 4),
                    "flagged": max_d > settings.SPEAKER_VERIFICATION_FLAG_DISTANCE,
                    "threshold": settings.SPEAKER_VERIFICATION_FLAG_DISTANCE,
                }
            )

    integrity = {
        # Each answer's first-word latency, plus per-candidate mean and
        # population variance. Constant cadence regardless of difficulty
        # is the highest-signal "tool in the loop" tell.
        "first_word_ms": {
            "values": latencies_ms,
            "mean": _mean([float(x) for x in latencies_ms]),
            "variance": _variance([float(x) for x in latencies_ms]),
            "count": len(latencies_ms),
        },
        "transcript_features": {
            "per_answer": feature_blobs,
            "structural_marker_total": sum(
                int(f.get("structural_marker_count", 0)) for f in feature_blobs
            ),
            "word_count_total": sum(int(f.get("word_count", 0)) for f in feature_blobs),
        },
        "speaker_verification": speaker_block,
        "proctoring_counts": proctoring_counts,
        # Kept for back-compat with existing callers; the real signal is
        # the proctoring counts above and the latency/vocab trends.
        "cheating_risk": candidate.cheating_risk,
    }

    return {
        "candidate": {
            "id": candidate.id,
            "name": candidate.name,
            "email": candidate.email,
            "status": candidate.status,
        },
        "interview": {
            "id": interview.id if interview else None,
            "role": interview.role if interview else "",
            "difficulty": interview.difficulty if interview else "",
            "status": interview.status if interview else "",
        },
        # `band` is the headline the recruiter UI must show. Raw scores are
        # retained for debugging and for the per-question breakdown but
        # should not be the headline number.
        "band": banding,
        "scores": {
            "final_score": candidate.final_score,
            "technical_score": technical_score,
            "communication_score": candidate.communication_score,
            "cheating_risk": candidate.cheating_risk,
        },
        "topic_scores": topic_averages,
        "integrity": integrity,
        "question_evaluations": question_evaluations,
        "total_questions": len(answers),
        "answered_questions": len([a for a in answers if a.transcript]),
    }
