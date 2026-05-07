from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


class RecruiterBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = Field(default=None, max_length=200)
    company: Optional[str] = Field(default=None, max_length=200)


class RecruiterCreate(RecruiterBase):
    password: str = Field(..., min_length=8, max_length=200)


class RecruiterResponse(RecruiterBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class TopicBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    skills: List[str] = Field(default_factory=list)


class TopicResponse(TopicBase):
    id: int

    class Config:
        from_attributes = True


class QuestionBase(BaseModel):
    question_text: str = Field(..., min_length=1, max_length=2000)
    topic_id: Optional[int] = None
    source: str = "system"


class QuestionResponse(QuestionBase):
    id: int
    interview_id: int
    # Phase 1: surfaced so the recruiter UI can show the rubric under
    # each preview question. `None` for legacy rows.
    rubric_json: Optional[dict] = None

    class Config:
        from_attributes = True


class QuestionCreateBody(BaseModel):
    """Body for the recruiter-side custom-question endpoint (ISSUE-17)."""
    question_text: str = Field(..., min_length=1, max_length=2000)


class InterviewBase(BaseModel):
    role: str = Field(..., min_length=1, max_length=200)
    difficulty: str = Field(default="medium", max_length=20)
    num_questions: int = Field(default=5, ge=1, le=50)
    skills: List[str] = Field(default_factory=list)


class InterviewCreate(InterviewBase):
    topics: List[int] = []
    custom_questions: List[str] = []
    # When the recruiter picks "Other" in the topic dropdown, the topic name
    # is sent here instead of (or in addition to) `topics`. Questions for this
    # topic are generated/looked up by name; no Topic row is auto-created so
    # the catalog stays curated.
    custom_topic: Optional[str] = Field(default=None, max_length=100)


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
    password: str = Field(..., min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CandidateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr


class CandidateCreate(CandidateBase):
    pass


class CandidateResponse(CandidateBase):
    id: int
    interview_id: int
    status: str
    final_score: Optional[float] = None
    communication_score: Optional[float] = None
    cheating_risk: str

    class Config:
        from_attributes = True


class CandidateRegistrationResponse(CandidateResponse):
    """Returned at the end of registration; includes the candidate session
    token used to authenticate subsequent candidate-flow requests."""
    session_token: str


class CandidateSummary(BaseModel):
    id: int
    name: str
    email: EmailStr
    status: str
    final_score: Optional[float] = None
    communication_score: Optional[float] = None
    cheating_risk: str
    # Phase 0.3: percentile band against the (role, difficulty) cohort.
    # `None` until the cohort reaches MIN_COHORT_SIZE, at which point the
    # endpoint fills it in. Recruiter UI should render `band` as the
    # headline; raw scores are kept for the debugger but should not be
    # the primary visual.
    band: Optional[str] = None
    cohort_size: Optional[int] = None

    class Config:
        from_attributes = True


class AnswerSubmittedResponse(BaseModel):
    """Response for POST /candidate/answer. Intentionally narrow — does NOT
    leak server-side fields like `audio_path` / `video_path` to the candidate."""
    id: int
    candidate_id: int
    question_id: int
    transcript: Optional[str] = None

    class Config:
        from_attributes = True


class ProctoringData(BaseModel):
    candidate_id: int
    events: List[dict]
    risk_level: str
    tab_switch_count: int
    clipboard_count: int


class ProctoringEventIn(BaseModel):
    """One proctoring event posted by the candidate's browser. `timestamp`
    is the client-side time the event happened (epoch ms); the server
    persists the receive-time on `ProctoringEvent.timestamp` instead — we
    don't trust client clocks."""
    event_type: str = Field(..., min_length=1, max_length=50)
    timestamp: Optional[int] = None
    details: Optional[dict] = None


class ProctoringEventsBatch(BaseModel):
    events: List[ProctoringEventIn]
