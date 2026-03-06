from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class RecruiterBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    company: Optional[str] = None

class RecruiterCreate(RecruiterBase):
    password: str

class RecruiterResponse(RecruiterBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class TopicBase(BaseModel):
    name: str
    description: Optional[str] = None

class TopicResponse(TopicBase):
    id: int
    
    class Config:
        from_attributes = True

class QuestionBase(BaseModel):
    question_text: str
    topic_id: Optional[int] = None
    source: str = "system"

class QuestionResponse(QuestionBase):
    id: int
    interview_id: int
    
    class Config:
        from_attributes = True

class InterviewBase(BaseModel):
    role: str
    difficulty: str = "medium"
    num_questions: int = 5

class InterviewCreate(InterviewBase):
    topics: List[int] = []
    custom_questions: List[str] = []

class InterviewResponse(InterviewBase):
    id: int
    recruiter_id: int
    interview_link: str
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class CandidateBase(BaseModel):
    name: str
    email: EmailStr

class CandidateCreate(CandidateBase):
    pass

class CandidateResponse(CandidateBase):
    id: int
    interview_id: int
    status: str
    final_score: Optional[float]
    communication_score: Optional[float]
    cheating_risk: str
    
    class Config:
        from_attributes = True

class ProctoringData(BaseModel):
    candidate_id: int
    events: List[dict]
    risk_level: str
    tab_switch_count: int
    clipboard_count: int
