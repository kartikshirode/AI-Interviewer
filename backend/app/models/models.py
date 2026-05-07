from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Text,
    Boolean,
    Index,
    JSON,
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
    # Curated skill catalog for this topic. Surfaced in the create-interview UI
    # alongside `GENERAL_SKILLS` (services/skills.py).
    skills = Column(JSON, nullable=False, default=list)

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
    # Free-text skill tags chosen by the recruiter at creation time.
    # Drives the question-bank lookup key and shows up in the report.
    skills = Column(JSON, nullable=False, default=list)
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


class ProctoringEvent(Base):
    """Per-candidate proctoring signals collected by the browser hook
    (`useProctoring`) during the interview.

    Each row is a single discrete event — tab switch, focus loss, clipboard
    interaction, etc. The candidate's frontend batches events and POSTs
    them to `/candidate/{candidate_id}/proctoring`. The recruiter's report
    reads from this table to compute counts per `event_type` and feed the
    `RiskEngine` for the cheating-risk level.

    `event_type` is intentionally a free-form string, not an enum, so the
    hook can extend the vocabulary (e.g. new keyboard shortcuts) without
    requiring a schema migration. The current vocabulary is documented in
    `useProctoring.ts` and `RiskEngine.WEIGHTS`.
    """

    __tablename__ = "proctoring_events"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(
        Integer,
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(50), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=_utcnow)
    # Optional per-event metadata (e.g. URL of opened tab, key name).
    # Kept as JSON so we don't have to migrate when a new field shows up.
    details = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_proctoring_events_candidate_type", "candidate_id", "event_type"),
    )


class QuestionBank(Base):
    """Persistent, reusable question pool keyed by (topic, difficulty, skills).

    Populated lazily: when an interview-creation flow needs questions for a
    (topic_name, difficulty, skills_key) tuple and the bank is short, the
    deficit is generated via Gemini and inserted here. Subsequent requests
    for the same key are served from the bank — random sample weighted by
    `times_used` ascending — so we don't burn API tokens on every preview.

    `topic_name` is a string, not an FK to `topics.id`, so questions for
    custom "Other" topics that aren't in the curated catalog still persist.
    """

    __tablename__ = "question_bank"

    id = Column(Integer, primary_key=True, index=True)
    topic_name = Column(String, nullable=False, index=True)
    difficulty = Column(String(20), nullable=False, index=True)
    # Normalized lookup key: lowercased, sorted, comma-joined skills. "" when no
    # skills picked. Indexed because every read filters on it.
    skills_key = Column(String, nullable=False, default="", index=True)
    # Original skills list (preserved case / order) for display + potential
    # downstream training. Not part of the lookup key.
    skills_json = Column(JSON, nullable=False, default=list)
    question_text = Column(Text, nullable=False)
    # Provenance: "gemini" / "static" / "manual". Helps later when training a
    # smart retriever — we'll want to weight manually-curated questions higher.
    source = Column(String, default="gemini")
    times_used = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=_utcnow)
    last_used_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "topic_name",
            "difficulty",
            "skills_key",
            "question_text",
            name="uq_question_bank_dedup",
        ),
        Index(
            "ix_question_bank_lookup",
            "topic_name",
            "difficulty",
            "skills_key",
            "times_used",
        ),
    )
