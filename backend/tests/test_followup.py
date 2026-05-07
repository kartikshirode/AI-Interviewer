"""Phase 2.4 — content-side follow-up generation.

Stubs out Gemini so these run offline. The behaviour under test is the
flag-gated trigger plus the two caps (one follow-up per original
question, max-per-interview).
"""

from __future__ import annotations

from unittest.mock import patch

from app.models.models import Answer, Candidate, Interview, Question, Recruiter
from app.routers.candidate import _maybe_generate_followup
from app.core.security import get_password_hash


VALID_RUBRIC = {
    "key_concepts": ["concept-A", "concept-B"],
    "anchors": {
        "0": "no",
        "1": "vague",
        "2": "partial",
        "3": "specific",
        "4": "exemplary",
    },
}


def _seed_strong_answer(db_session, *, source: str = "system"):
    """Return a (question, answer) pair where the answer scored 3/4."""
    rec = Recruiter(email="rfu@x.com", hashed_password=get_password_hash("longpass1234"))
    db_session.add(rec)
    db_session.commit()

    iv = Interview(
        recruiter_id=rec.id,
        role="SWE",
        difficulty="medium",
        num_questions=1,
        interview_link="link-fu",
        status="active",
        skills=[],
    )
    db_session.add(iv)
    db_session.commit()

    q = Question(
        interview_id=iv.id,
        question_text="explain the GIL",
        rubric_json=VALID_RUBRIC,
        source=source,
    )
    db_session.add(q)
    db_session.commit()

    cand = Candidate(
        interview_id=iv.id,
        name="C",
        email="cfu@x.com",
        status="in_progress",
    )
    db_session.add(cand)
    db_session.commit()

    ans = Answer(
        candidate_id=cand.id,
        question_id=q.id,
        whisper_transcript="The GIL serializes Python bytecode execution",
        rubric_score=3,
    )
    db_session.add(ans)
    db_session.commit()
    return iv, q, ans


def test_followup_skipped_when_flag_off(db_session, monkeypatch):
    """Default config has ENABLE_FOLLOWUP_QUESTIONS=False — generator
    must not be called."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENABLE_FOLLOWUP_QUESTIONS", False)
    _, q, ans = _seed_strong_answer(db_session)

    sentinel = {"called": False}

    def boom(self, *a, **kw):
        sentinel["called"] = True
        return ("never-asked", VALID_RUBRIC)

    with patch(
        "app.services.question_generator.QuestionGenerator.generate_followup",
        new=boom,
    ):
        _maybe_generate_followup(db_session, ans)

    assert sentinel["called"] is False
    # No new Question rows.
    assert (
        db_session.query(Question).filter_by(interview_id=q.interview_id).count() == 1
    )


def test_followup_generated_when_score_meets_threshold(db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENABLE_FOLLOWUP_QUESTIONS", True)
    monkeypatch.setattr(settings, "FOLLOWUP_THRESHOLD", 3.0)
    _, q, ans = _seed_strong_answer(db_session)

    def fake_followup(self, question, transcript, rubric, topic, difficulty):
        return ("you said the GIL serializes bytecode — what does multiprocessing change?", VALID_RUBRIC)

    with patch(
        "app.services.question_generator.QuestionGenerator.generate_followup",
        new=fake_followup,
    ):
        _maybe_generate_followup(db_session, ans)

    new_qs = (
        db_session.query(Question)
        .filter(Question.parent_question_id == q.id)
        .all()
    )
    assert len(new_qs) == 1
    assert new_qs[0].source == "followup"
    assert new_qs[0].rubric_json == VALID_RUBRIC
    assert "GIL" in new_qs[0].question_text


def test_followup_skipped_below_threshold(db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENABLE_FOLLOWUP_QUESTIONS", True)
    monkeypatch.setattr(settings, "FOLLOWUP_THRESHOLD", 3.0)
    _, q, ans = _seed_strong_answer(db_session)
    ans.rubric_score = 2  # below threshold
    db_session.commit()

    sentinel = {"called": False}

    def boom(self, *a, **kw):
        sentinel["called"] = True
        return ("nope", None)

    with patch(
        "app.services.question_generator.QuestionGenerator.generate_followup",
        new=boom,
    ):
        _maybe_generate_followup(db_session, ans)

    assert sentinel["called"] is False
    assert (
        db_session.query(Question).filter_by(interview_id=q.interview_id).count() == 1
    )


def test_followup_skipped_when_one_already_exists(db_session, monkeypatch):
    """Cap 1: one follow-up per original question."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENABLE_FOLLOWUP_QUESTIONS", True)
    iv, q, ans = _seed_strong_answer(db_session)

    db_session.add(
        Question(
            interview_id=iv.id,
            topic_id=None,
            question_text="prior follow-up",
            source="followup",
            parent_question_id=q.id,
        )
    )
    db_session.commit()

    sentinel = {"called": False}

    def boom(self, *a, **kw):
        sentinel["called"] = True
        return ("nope", None)

    with patch(
        "app.services.question_generator.QuestionGenerator.generate_followup",
        new=boom,
    ):
        _maybe_generate_followup(db_session, ans)

    assert sentinel["called"] is False
    children = (
        db_session.query(Question).filter(Question.parent_question_id == q.id).count()
    )
    assert children == 1


def test_followup_respects_max_per_interview(db_session, monkeypatch):
    """Cap 2: MAX_FOLLOWUPS_PER_INTERVIEW. Set the cap to 1 to keep the
    fixture small; the production default is 3."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENABLE_FOLLOWUP_QUESTIONS", True)
    monkeypatch.setattr(settings, "MAX_FOLLOWUPS_PER_INTERVIEW", 1)
    iv, q, ans = _seed_strong_answer(db_session)

    # Pre-seed one follow-up off a different parent so it doesn't trip
    # the per-question cap, but does trip the per-interview cap.
    other_q = Question(
        interview_id=iv.id,
        question_text="another",
        source="system",
    )
    db_session.add(other_q)
    db_session.commit()
    db_session.add(
        Question(
            interview_id=iv.id,
            question_text="existing follow-up",
            source="followup",
            parent_question_id=other_q.id,
        )
    )
    db_session.commit()

    sentinel = {"called": False}

    def boom(self, *a, **kw):
        sentinel["called"] = True
        return ("nope", None)

    with patch(
        "app.services.question_generator.QuestionGenerator.generate_followup",
        new=boom,
    ):
        _maybe_generate_followup(db_session, ans)

    assert sentinel["called"] is False


def test_followup_skipped_when_parent_is_itself_a_followup(db_session, monkeypatch):
    """Don't recurse: a follow-up never gets its own follow-up."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENABLE_FOLLOWUP_QUESTIONS", True)
    _, q, ans = _seed_strong_answer(db_session, source="followup")

    sentinel = {"called": False}

    def boom(self, *a, **kw):
        sentinel["called"] = True
        return ("nope", None)

    with patch(
        "app.services.question_generator.QuestionGenerator.generate_followup",
        new=boom,
    ):
        _maybe_generate_followup(db_session, ans)

    assert sentinel["called"] is False
