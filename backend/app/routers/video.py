import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Answer, Candidate, Interview, Recruiter
from app.routers.auth import get_current_recruiter

router = APIRouter(prefix="/videos", tags=["Video"])


@router.get("/{answer_id}")
def get_video(
    answer_id: int,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    answer = db.query(Answer).filter(Answer.id == answer_id).first()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    # Ownership check: the answer must belong to a candidate of an interview
    # owned by the calling recruiter.
    candidate = (
        db.query(Candidate).filter(Candidate.id == answer.candidate_id).first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Answer not found")

    interview = (
        db.query(Interview)
        .filter(
            Interview.id == candidate.interview_id,
            Interview.recruiter_id == recruiter.id,
        )
        .first()
    )
    if not interview:
        # Don't leak existence of an answer the recruiter does not own.
        raise HTTPException(status_code=404, detail="Answer not found")

    if not answer.video_path or not os.path.exists(answer.video_path):
        raise HTTPException(status_code=404, detail="Video not found")

    return FileResponse(
        answer.video_path,
        media_type="video/webm",
        headers={"Content-Disposition": f"inline; filename=answer_{answer_id}.webm"},
    )
