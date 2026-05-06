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
from typing import List, Optional

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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_candidate_token
from app.models.models import Answer, Candidate, Interview, Question, Recruiter, Topic
from app.models.schemas import (
    AnswerSubmittedResponse,
    CandidateCreate,
    CandidateRegistrationResponse,
    CandidateResponse,
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
    interview = db.query(Interview).filter(Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

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
        db.commit()
        db.refresh(db_candidate)
    else:
        db_candidate = Candidate(
            interview_id=interview_id,
            name=candidate.name,
            email=candidate.email,
            status="registered",
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


def _transcribe_audio_background(answer_id: int, audio_path: str):
    """Background task: run Whisper on recorded audio and update the answer.

    Failures are logged and persisted onto `Answer.flag_reason` so the
    recruiter sees that transcription couldn't run, instead of silently
    leaving `whisper_transcript = NULL` and pretending nothing happened.
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
    audio: Optional[UploadFile] = File(None),
    video: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    candidate: Candidate = Depends(get_current_candidate),
):
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
    )

    if not evaluation.get("_ok", False):
        # Don't persist a dummy evaluation; bubble the error.
        raise HTTPException(
            status_code=502,
            detail=f"Evaluation failed: {evaluation.get('_error', 'unknown error')}",
        )

    answer.correctness = evaluation["correctness"]
    answer.clarity = evaluation["clarity"]
    answer.depth = evaluation["depth"]
    answer.confidence_score = evaluation.get("confidence")
    answer.feedback = evaluation.get("feedback", "")
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
        )

        if not evaluation.get("_ok", False):
            # Skip this answer's persisted score on failure rather than
            # poisoning the DB with dummies.
            continue

        answer.correctness = evaluation["correctness"]
        answer.clarity = evaluation["clarity"]
        answer.depth = evaluation["depth"]
        answer.confidence_score = evaluation.get("confidence")
        answer.feedback = evaluation.get("feedback", "")
        answer_evaluations.append(evaluation)

    all_transcripts = "\n\n".join(
        (a.whisper_transcript or a.transcript)
        for a in answers
        if (a.whisper_transcript or a.transcript)
    )
    comm_eval = evaluation_service.evaluate_communication(
        all_transcripts, len(answers)
    )

    final_scores = evaluation_service.calculate_final_score(
        answer_evaluations, comm_eval["communication_score"]
    )

    if final_scores is None:
        db.commit()
        raise HTTPException(
            status_code=502,
            detail="No answers could be evaluated successfully",
        )

    candidate.final_score = final_scores["final_score"]
    candidate.communication_score = comm_eval["communication_score"]
    db.commit()

    return {
        "final_score": final_scores["final_score"],
        "technical_score": final_scores["technical_score"],
        "communication_score": final_scores["communication_score"],
        "answer_evaluations": answer_evaluations,
        "communication_evaluation": comm_eval,
    }


@router.post("/candidate/{candidate_id}/proctoring")
def save_proctoring_data(
    candidate_id: int,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    """Persist proctoring events for a candidate.

    TODO(persistence): this currently does NOT save the posted events to a
    dedicated `ProctoringEvent` table — that schema migration is intentionally
    out of scope for this audit pass. The endpoint validates ownership and
    acknowledges receipt; risk computation is done at /proctoring/report time
    using the flags already attached to Answer rows.
    """
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_owns_candidate(db, recruiter, candidate)

    return {
        "status": "received",
        "candidate_id": candidate_id,
        "persisted": False,
        "note": (
            "Events are not yet persisted to a ProctoringEvent table. "
            "Risk score is currently computed from per-answer flags only."
        ),
    }


@router.post("/candidate/{candidate_id}/proctoring/report")
def get_proctoring_report(
    candidate_id: int,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    """Get proctoring report for a candidate."""
    from app.services.risk_engine import RiskEngine

    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _ensure_owns_candidate(db, recruiter, candidate)

    answers = db.query(Answer).filter(Answer.candidate_id == candidate_id).all()

    tab_switch_count = sum(
        1 for a in answers if a.is_flagged and a.flag_reason == "tab_switch"
    )
    clipboard_count = sum(
        1 for a in answers if a.is_flagged and a.flag_reason == "clipboard"
    )

    risk_result = RiskEngine.calculate_combined_risk(
        tab_switches=tab_switch_count,
        clipboard_pastes=clipboard_count,
    )

    candidate.cheating_risk = risk_result["risk_level"]
    db.commit()

    return risk_result


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

        question_evaluations.append(
            {
                "question_id": question.id if question else None,
                "question_text": question.question_text if question else "",
                "topic": topic,
                "transcript": answer.transcript,
                "video_path": answer.video_path,
                "correctness": answer.correctness,
                "clarity": answer.clarity,
                "depth": answer.depth,
                "is_flagged": answer.is_flagged,
                "flag_reason": answer.flag_reason,
            }
        )

        if topic and answer.correctness is not None:
            bucket = topic_scores.setdefault(topic, {"total": 0.0, "count": 0})
            bucket["total"] += answer.correctness
            bucket["count"] += 1

        # Re-use the same shape evaluation_service expects for aggregation.
        if answer.correctness is not None:
            answer_eval_dicts.append(
                {
                    "correctness": answer.correctness,
                    "clarity": answer.clarity if answer.clarity is not None else 5,
                    "depth": answer.depth if answer.depth is not None else 5,
                }
            )

    topic_averages = {
        t: round(d["total"] / d["count"], 2) if d["count"] > 0 else 0
        for t, d in topic_scores.items()
    }

    # Use the same formula as evaluation_service.calculate_final_score for
    # consistency (ISSUE-28).
    comm_score = candidate.communication_score or 0
    aggregated = evaluation_service.calculate_final_score(answer_eval_dicts, comm_score)
    technical_score = aggregated["technical_score"] if aggregated else None

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
        "scores": {
            "final_score": candidate.final_score,
            "technical_score": technical_score,
            "communication_score": candidate.communication_score,
            "cheating_risk": candidate.cheating_risk,
        },
        "topic_scores": topic_averages,
        "question_evaluations": question_evaluations,
        "total_questions": len(answers),
        "answered_questions": len([a for a in answers if a.transcript]),
    }
