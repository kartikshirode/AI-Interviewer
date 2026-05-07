"""Phase 2.2 — speaker verification.

speechbrain is intentionally NOT a hard dependency, so these tests
stub `extract_embedding` rather than calling the real model. Behaviour
under test:
- cosine_distance math is sound.
- Registration refuses without consent when the flag is on.
- Registration accepts and records voice_consent_at when consent is given.
- The integrity panel surfaces speaker-verification stats from
  pre-existing voice_embedding blobs.
- Service degrades gracefully when speechbrain isn't installed.
"""

from __future__ import annotations

from app.models.models import Answer, Candidate
from app.services.speaker_verification import cosine_distance, is_available


def test_cosine_distance_identical_vectors():
    """Same vector → distance 0."""
    a = [1.0, 2.0, 3.0]
    assert cosine_distance(a, a) == 0.0


def test_cosine_distance_orthogonal_vectors():
    """Orthogonal vectors → distance 1.0."""
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert cosine_distance(a, b) == 1.0


def test_cosine_distance_anti_parallel():
    """Opposing vectors → distance 2.0."""
    assert cosine_distance([1.0, 0.0], [-1.0, 0.0]) == 2.0


def test_cosine_distance_handles_invalid_inputs():
    """Missing / zero-norm / mismatched-length inputs return None,
    not a fabricated 'they're different' signal."""
    assert cosine_distance(None, [1.0]) is None
    assert cosine_distance([], []) is None
    assert cosine_distance([1.0, 2.0], [1.0]) is None
    assert cosine_distance([0.0, 0.0], [0.0, 0.0]) is None


def test_is_available_does_not_crash_without_speechbrain():
    """Should return a bool either way — the call must never raise
    even when speechbrain is missing from the env."""
    result = is_available()
    assert isinstance(result, bool)


# ── Registration consent gating ────────────────────────────────────────────


def test_register_refused_without_consent_when_flag_on(client, db_session, monkeypatch):
    from app.core.config import settings as _settings

    monkeypatch.setattr(_settings, "ENABLE_SPEAKER_VERIFICATION", True)

    # Set up a recruiter + interview directly so the test stays small.
    from app.models.models import Recruiter, Interview
    from app.core.security import get_password_hash

    rec = Recruiter(email="rsv@x.com", hashed_password=get_password_hash("longpass1234"))
    db_session.add(rec)
    db_session.commit()
    iv = Interview(
        recruiter_id=rec.id,
        role="SWE",
        difficulty="medium",
        num_questions=1,
        interview_link="link-sv",
        status="active",
        skills=[],
    )
    db_session.add(iv)
    db_session.commit()

    # No voice_consent in body.
    r = client.post(
        f"/api/v1/candidate/interview/{iv.id}/register",
        json={"name": "C", "email": "csv@x.com"},
    )
    assert r.status_code == 400
    assert "consent" in r.json()["detail"].lower()
    # And again with explicit False.
    r = client.post(
        f"/api/v1/candidate/interview/{iv.id}/register",
        json={"name": "C", "email": "csv@x.com", "voice_consent": False},
    )
    assert r.status_code == 400


def test_register_records_consent_timestamp(client, db_session, monkeypatch):
    from app.core.config import settings as _settings
    from app.models.models import Recruiter, Interview
    from app.core.security import get_password_hash

    monkeypatch.setattr(_settings, "ENABLE_SPEAKER_VERIFICATION", True)

    rec = Recruiter(email="rsv2@x.com", hashed_password=get_password_hash("longpass1234"))
    db_session.add(rec)
    db_session.commit()
    iv = Interview(
        recruiter_id=rec.id,
        role="SWE",
        difficulty="medium",
        num_questions=1,
        interview_link="link-sv2",
        status="active",
        skills=[],
    )
    db_session.add(iv)
    db_session.commit()

    r = client.post(
        f"/api/v1/candidate/interview/{iv.id}/register",
        json={"name": "C", "email": "csv2@x.com", "voice_consent": True},
    )
    assert r.status_code == 201
    body = r.json()
    cand = db_session.query(Candidate).filter_by(id=body["id"]).one()
    assert cand.voice_consent_at is not None


def test_register_consent_optional_when_flag_off(client, db_session, monkeypatch):
    """Default config: feature off → consent field is optional, registration
    must work without it for existing client code."""
    from app.core.config import settings as _settings
    from app.models.models import Recruiter, Interview
    from app.core.security import get_password_hash

    monkeypatch.setattr(_settings, "ENABLE_SPEAKER_VERIFICATION", False)

    rec = Recruiter(email="rsv3@x.com", hashed_password=get_password_hash("longpass1234"))
    db_session.add(rec)
    db_session.commit()
    iv = Interview(
        recruiter_id=rec.id,
        role="SWE",
        difficulty="medium",
        num_questions=1,
        interview_link="link-sv3",
        status="active",
        skills=[],
    )
    db_session.add(iv)
    db_session.commit()

    r = client.post(
        f"/api/v1/candidate/interview/{iv.id}/register",
        json={"name": "C", "email": "csv3@x.com"},
    )
    assert r.status_code == 201


# ── Integrity panel exposes speaker_verification stats ─────────────────────


def test_integrity_panel_includes_speaker_verification(client, db_session, monkeypatch):
    """When two answers carry voice embeddings, the report reports
    mean / max distance and a flagged boolean."""
    from app.core.config import settings as _settings
    from app.core.security import get_password_hash
    from app.models.models import Recruiter, Interview, Question

    monkeypatch.setattr(_settings, "ENABLE_SPEAKER_VERIFICATION", True)
    monkeypatch.setattr(_settings, "SPEAKER_VERIFICATION_FLAG_DISTANCE", 0.3)

    rec = Recruiter(email="rsv4@x.com", hashed_password=get_password_hash("longpass1234"))
    db_session.add(rec)
    db_session.commit()
    iv = Interview(
        recruiter_id=rec.id,
        role="SWE",
        difficulty="medium",
        num_questions=2,
        interview_link="link-sv4",
        status="active",
        skills=[],
    )
    db_session.add(iv)
    db_session.commit()

    q1 = Question(interview_id=iv.id, question_text="q1", source="system")
    q2 = Question(interview_id=iv.id, question_text="q2", source="system")
    db_session.add_all([q1, q2])
    db_session.commit()

    cand = Candidate(
        interview_id=iv.id,
        name="C",
        email="csv4@x.com",
        status="completed",
        voice_consent_at=__import__("datetime").datetime.now(),
    )
    db_session.add(cand)
    db_session.commit()

    # Answer 1: reference embedding.
    db_session.add(
        Answer(
            candidate_id=cand.id,
            question_id=q1.id,
            transcript="hi",
            voice_embedding=[1.0, 0.0, 0.0],
        )
    )
    # Answer 2: orthogonal → cosine_distance = 1.0 (should flag).
    db_session.add(
        Answer(
            candidate_id=cand.id,
            question_id=q2.id,
            transcript="hi",
            voice_embedding=[0.0, 1.0, 0.0],
        )
    )
    db_session.commit()

    rtok = client.post(
        "/api/v1/auth/login",
        json={"email": rec.email, "password": "longpass1234"},
    ).json()["access_token"]

    r = client.get(
        f"/api/v1/candidate/candidate/{cand.id}/report",
        headers={"Authorization": f"Bearer {rtok}"},
    )
    assert r.status_code == 200
    sv = r.json()["integrity"]["speaker_verification"]
    assert sv["enabled"] is True
    assert sv["consent_recorded"] is True
    assert sv["answer_count"] == 2
    assert sv["mean_distance"] == 1.0
    assert sv["max_distance"] == 1.0
    assert sv["flagged"] is True


def test_integrity_panel_omits_distance_when_only_one_embedding(
    client, db_session, monkeypatch
):
    """Single embedded answer = no comparison possible. Block reports
    the count but no mean/max — and never invents a flag."""
    from app.core.config import settings as _settings
    from app.core.security import get_password_hash
    from app.models.models import Recruiter, Interview, Question

    monkeypatch.setattr(_settings, "ENABLE_SPEAKER_VERIFICATION", True)

    rec = Recruiter(email="rsv5@x.com", hashed_password=get_password_hash("longpass1234"))
    db_session.add(rec)
    db_session.commit()
    iv = Interview(
        recruiter_id=rec.id,
        role="SWE",
        difficulty="medium",
        num_questions=1,
        interview_link="link-sv5",
        status="active",
        skills=[],
    )
    db_session.add(iv)
    db_session.commit()
    q = Question(interview_id=iv.id, question_text="q", source="system")
    db_session.add(q)
    db_session.commit()
    cand = Candidate(
        interview_id=iv.id,
        name="C",
        email="csv5@x.com",
        status="completed",
        voice_consent_at=__import__("datetime").datetime.now(),
    )
    db_session.add(cand)
    db_session.commit()
    db_session.add(
        Answer(
            candidate_id=cand.id,
            question_id=q.id,
            voice_embedding=[1.0, 0.0],
        )
    )
    db_session.commit()

    rtok = client.post(
        "/api/v1/auth/login",
        json={"email": rec.email, "password": "longpass1234"},
    ).json()["access_token"]

    r = client.get(
        f"/api/v1/candidate/candidate/{cand.id}/report",
        headers={"Authorization": f"Bearer {rtok}"},
    )
    assert r.status_code == 200
    sv = r.json()["integrity"]["speaker_verification"]
    assert sv["answer_count"] == 1
    assert "max_distance" not in sv
    assert "flagged" not in sv
