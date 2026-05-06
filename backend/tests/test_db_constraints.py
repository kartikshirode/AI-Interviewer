"""ISSUE-34 cascade-delete + ISSUE-35 unique constraint."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.models import Answer, Candidate, Interview, Question, Recruiter


def test_cascade_delete_recruiter_drops_children(db_session):
    rec = Recruiter(email="r@x.com", hashed_password="x", full_name="R")
    db_session.add(rec)
    db_session.commit()

    iv = Interview(
        recruiter_id=rec.id,
        role="X",
        difficulty="medium",
        num_questions=1,
        interview_link="abc",
    )
    db_session.add(iv)
    db_session.commit()

    q = Question(interview_id=iv.id, question_text="Q?")
    db_session.add(q)
    cand = Candidate(interview_id=iv.id, name="N", email="n@x.com")
    db_session.add(cand)
    db_session.commit()
    ans = Answer(candidate_id=cand.id, question_id=q.id, transcript="hi")
    db_session.add(ans)
    db_session.commit()

    iv_id = iv.id
    cand_id = cand.id
    ans_id = ans.id
    q_id = q.id

    # Deleting the recruiter must also drop interview / question / candidate / answer
    db_session.delete(rec)
    db_session.commit()

    assert db_session.query(Interview).filter_by(id=iv_id).first() is None
    assert db_session.query(Question).filter_by(id=q_id).first() is None
    assert db_session.query(Candidate).filter_by(id=cand_id).first() is None
    assert db_session.query(Answer).filter_by(id=ans_id).first() is None


def test_cascade_delete_interview_drops_candidates_questions(db_session):
    rec = Recruiter(email="r2@x.com", hashed_password="x")
    db_session.add(rec)
    db_session.commit()
    iv = Interview(
        recruiter_id=rec.id,
        role="X",
        difficulty="medium",
        num_questions=1,
        interview_link="link2",
    )
    db_session.add(iv)
    db_session.commit()
    q = Question(interview_id=iv.id, question_text="Q?")
    cand = Candidate(interview_id=iv.id, name="N", email="n@x.com")
    db_session.add_all([q, cand])
    db_session.commit()
    iv_id, q_id, cand_id = iv.id, q.id, cand.id

    db_session.delete(iv)
    db_session.commit()
    assert db_session.query(Question).filter_by(id=q_id).first() is None
    assert db_session.query(Candidate).filter_by(id=cand_id).first() is None


def test_candidate_unique_per_interview_email(db_session):
    """ISSUE-35: same email can register for two different interviews, but
    NOT twice for the same interview at the DB level."""
    rec = Recruiter(email="r3@x.com", hashed_password="x")
    db_session.add(rec)
    db_session.commit()
    iv1 = Interview(
        recruiter_id=rec.id,
        role="X",
        difficulty="medium",
        num_questions=1,
        interview_link="iv1",
    )
    iv2 = Interview(
        recruiter_id=rec.id,
        role="Y",
        difficulty="medium",
        num_questions=1,
        interview_link="iv2",
    )
    db_session.add_all([iv1, iv2])
    db_session.commit()

    db_session.add(Candidate(interview_id=iv1.id, name="N", email="dup@x.com"))
    db_session.commit()

    # Different interview, same email — fine
    db_session.add(Candidate(interview_id=iv2.id, name="N", email="dup@x.com"))
    db_session.commit()

    # Same interview, same email — IntegrityError
    db_session.add(Candidate(interview_id=iv1.id, name="N2", email="dup@x.com"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_answer_unique_per_candidate_question(db_session):
    rec = Recruiter(email="r4@x.com", hashed_password="x")
    db_session.add(rec)
    db_session.commit()
    iv = Interview(
        recruiter_id=rec.id,
        role="X",
        difficulty="medium",
        num_questions=1,
        interview_link="iv4",
    )
    db_session.add(iv)
    db_session.commit()
    q = Question(interview_id=iv.id, question_text="Q?")
    cand = Candidate(interview_id=iv.id, name="N", email="n@x.com")
    db_session.add_all([q, cand])
    db_session.commit()

    db_session.add(Answer(candidate_id=cand.id, question_id=q.id, transcript="a"))
    db_session.commit()
    db_session.add(Answer(candidate_id=cand.id, question_id=q.id, transcript="b"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
