from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import os

from app.core.database import get_db
from app.models.models import Answer, Candidate

router = APIRouter(prefix="/videos", tags=["Video"])

@router.get("/{answer_id}")
def get_video(answer_id: int, db: Session = Depends(get_db)):
    answer = db.query(Answer).filter(Answer.id == answer_id).first()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")
    
    if not answer.video_path or not os.path.exists(answer.video_path):
        raise HTTPException(status_code=404, detail="Video not found")
    
    return FileResponse(
        answer.video_path,
        media_type="video/webm",
        headers={"Content-Disposition": f"inline; filename=answer_{answer_id}.webm"}
    )
