from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.models.models import Interview, Candidate
from app.services.livekit_service import livekit_service

router = APIRouter(prefix="/voice", tags=["Voice Interview"])

class VoiceTokenRequest(BaseModel):
    interview_id: int
    candidate_id: int

class VoiceTokenResponse(BaseModel):
    token: str
    room_name: str
    url: str

@router.post("/token", response_model=VoiceTokenResponse)
def get_voice_token(
    request: VoiceTokenRequest,
    db: Session = Depends(get_db)
):
    """Generate LiveKit token for voice interview"""
    try:
        interview = db.query(Interview).filter(Interview.id == request.interview_id).first()
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")
        
        candidate = db.query(Candidate).filter(
            Candidate.id == request.candidate_id,
            Candidate.interview_id == request.interview_id
        ).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        
        room_name = f"interview_{request.interview_id}_candidate_{request.candidate_id}"
        
        token = livekit_service.generate_token(
            room_name=room_name,
            participant_name=str(candidate.name),
            is_agent=False
        )
        
        return VoiceTokenResponse(
            token=token,
            room_name=room_name,
            url=livekit_service.url
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
