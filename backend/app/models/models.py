from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Text,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Recruiter(Base):
    __tablename__ = "recruiters"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    company = Column(String)
    created_at = Column(DateTime, default=_utcnow)

    interviews = relationship(
        "Interview", back_populates="recruiter", cascade="all, delete-orphan"
    )


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String)

    questions = relationship("Question", back_populates="topic")


class Interview(Base):
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    recruiter_id = Column(
        Integer, ForeignKey("recruiters.id", ondelete="CASCADE"), index=True
    )
    role = Column(String, nullable=False)
    difficulty = Column(String, default="medium")
    num_questions = Column(Integer, default=5)
    interview_link = Column(String, unique=True, index=True)
    status = Column(String, default="draft")
    created_at = Column(DateTime, default=_utcnow)
    expires_at = Column(DateTime, nullable=True)

    recruiter = relationship("Recruiter", back_populates="interviews")
    questions = relationship(
        "Question", back_populates="interview", cascade="all, delete-orphan"
    )
    candidates = relationship(
        "Candidate", back_populates="interview", cascade="all, delete-orphan"
    )


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    interview_id = Column(
        Integer,
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_id = Column(
        Integer, ForeignKey("topics.id"), nullable=True, index=True
    )
    question_text = Column(Text, nullable=False)
    source = Column(String, default="system")
    created_at = Column(DateTime, default=_utcnow)

    interview = relationship("Interview", back_populates="questions")
    topic = relationship("Topic", back_populates="questions")
    answers = relationship(
        "Answer", back_populates="question", cascade="all, delete-orphan"
    )


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    interview_id = Column(
        Integer, ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    status = Column(String, default="pending")
    final_score = Column(Float, nullable=True)
    communication_score = Column(Float, nullable=True)
    cheating_risk = Column(String, default="low")
    created_at = Column(DateTime, default=_utcnow)

    interview = relationship("Interview", back_populates="candidates")
    answers = relationship(
        "Answer", back_populates="candidate", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("interview_id", "email", name="uq_candidate_interview_email"),
    )


class Answer(Base):
    __tablename__ = "answers"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(
        Integer, ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    question_id = Column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    transcript = Column(Text, nullable=True)           # real-time Web Speech API transcript
    whisper_transcript = Column(Text, nullable=True)   # high-accuracy Whisper transcript
    audio_path = Column(String, nullable=True)         # recorded audio file path
    video_path = Column(String, nullable=True)
    correctness = Column(Float, nullable=True)
    clarity = Column(Float, nullable=True)
    depth = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=True)
    feedback = Column(Text, nullable=True)
    is_flagged = Column(Boolean, default=False)
    flag_reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    question = relationship("Question", back_populates="answers")
    candidate = relationship("Candidate", back_populates="answers")

    __table_args__ = (
        UniqueConstraint("candidate_id", "question_id", name="uq_answer_candidate_question"),
    )
