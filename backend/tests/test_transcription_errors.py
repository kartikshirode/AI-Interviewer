"""Phase 0.5 regression: real Whisper failures must surface as
`flag_reason = "transcription_failed"` on the Answer row.

Before this fix, `speech_service.transcribe_audio` swallowed every
exception internally and returned "" — which the background task then
misclassified as "transcription_empty" (silence). The except branch in
the task that set `transcription_failed` was unreachable.
"""

from __future__ import annotations

from unittest.mock import patch

from app.models.models import Answer, Candidate, Interview, Question, Recruiter
from app.routers.candidate import _transcribe_audio_background
from app.core.security import get_password_hash


def _seed_answer(db_session) -> Answer:
    rec = Recruiter(email="r@x.com", hashed_password=get_password_hash("longpass1234"))
    db_session.add(rec)
    db_session.commit()
    db_session.refresh(rec)

    iv = Interview(
        recruiter_id=rec.id,
        role="SWE",
        difficulty="medium",
        num_questions=1,
        interview_link="link-x",
        status="active",
        skills=[],
    )
    db_session.add(iv)
    db_session.commit()
    db_session.refresh(iv)

    q = Question(interview_id=iv.id, question_text="q?", source="system")
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)

    cand = Candidate(
        interview_id=iv.id, name="C", email="c@x.com", status="in_progress"
    )
    db_session.add(cand)
    db_session.commit()
    db_session.refresh(cand)

    ans = Answer(candidate_id=cand.id, question_id=q.id, transcript="hi")
    db_session.add(ans)
    db_session.commit()
    db_session.refresh(ans)
    return ans


def test_real_whisper_failure_sets_flag_reason(db_session, tmp_path, monkeypatch):
    """Phase 0.5: when speech_service.transcribe_audio raises, the
    background task must persist `flag_reason = "transcription_failed"`
    on the Answer row — not the misclassified "transcription_empty"."""
    ans = _seed_answer(db_session)

    audio_file = tmp_path / "fake.webm"
    audio_file.write_bytes(b"\x1aE\xdf\xa3 not really webm")

    # The background task uses its own SessionLocal, not db_session — so
    # we have to monkeypatch the module-level SessionLocal too if we
    # want the write to land in this engine. The conftest's `client`
    # fixture overrides get_db, but `_transcribe_audio_background`
    # imports SessionLocal directly. Easiest path: pre-bind a Session
    # factory bound to the test engine.
    from app.core import database as core_db
    bind_engine = db_session.get_bind()
    from sqlalchemy.orm import sessionmaker

    test_session_factory = sessionmaker(
        autocommit=False, autoflush=False, bind=bind_engine
    )
    monkeypatch.setattr(core_db, "SessionLocal", test_session_factory)

    # Force speech_service.transcribe_audio to raise — the propagation
    # is the actual thing under test.
    def boom(self, path):
        raise RuntimeError("Whisper exploded")

    from app.services.speech_service import SpeechToTextService
    monkeypatch.setattr(SpeechToTextService, "transcribe_audio", boom)

    _transcribe_audio_background(ans.id, str(audio_file))

    db_session.expire_all()
    refreshed = db_session.query(Answer).filter(Answer.id == ans.id).first()
    assert refreshed is not None
    assert refreshed.flag_reason == "transcription_failed"
    assert refreshed.whisper_transcript is None


def test_empty_transcript_still_classified_as_empty(db_session, tmp_path, monkeypatch):
    """Sanity: a successful but empty Whisper result is `transcription_empty`,
    not `transcription_failed`. The two states must remain distinguishable."""
    ans = _seed_answer(db_session)

    audio_file = tmp_path / "silent.webm"
    audio_file.write_bytes(b"silent")

    from app.core import database as core_db
    from sqlalchemy.orm import sessionmaker

    test_session_factory = sessionmaker(
        autocommit=False, autoflush=False, bind=db_session.get_bind()
    )
    monkeypatch.setattr(core_db, "SessionLocal", test_session_factory)

    from app.services.speech_service import SpeechToTextService
    monkeypatch.setattr(SpeechToTextService, "transcribe_audio", lambda self, p: "")

    _transcribe_audio_background(ans.id, str(audio_file))

    db_session.expire_all()
    refreshed = db_session.query(Answer).filter(Answer.id == ans.id).first()
    assert refreshed is not None
    assert refreshed.flag_reason == "transcription_empty"
