"""Tests for the proctoring persistence path (Phase 0.2).

Before Phase 0.2 the POST endpoint returned `{persisted: false}` and the
report endpoint scanned `Answer.flag_reason` for strings nothing ever
wrote. This file pins the new behaviour so the regression can't reopen.
"""

from __future__ import annotations

from app.models.models import Candidate, Interview, ProctoringEvent, Recruiter
from app.core.security import create_candidate_token, get_password_hash


def _seed_recruiter_with_candidate(db_session, *, recruiter_email="r1@x.com"):
    """Create one recruiter, one interview, one candidate. Returns
    (recruiter, candidate) plus a candidate session token."""
    rec = Recruiter(
        email=recruiter_email,
        hashed_password=get_password_hash("longpass1234"),
    )
    db_session.add(rec)
    db_session.commit()
    db_session.refresh(rec)

    iv = Interview(
        recruiter_id=rec.id,
        role="SWE",
        difficulty="medium",
        num_questions=3,
        interview_link=f"link-{rec.id}",
        status="active",
        skills=[],
    )
    db_session.add(iv)
    db_session.commit()
    db_session.refresh(iv)

    cand = Candidate(
        interview_id=iv.id,
        name="Test Candidate",
        email=f"c-{rec.id}@x.com",
        status="in_progress",
    )
    db_session.add(cand)
    db_session.commit()
    db_session.refresh(cand)

    cand_token = create_candidate_token(cand.id, iv.id)
    return rec, cand, cand_token


def test_save_proctoring_persists_events(client, db_session):
    """POSTing events with the candidate token writes ProctoringEvent rows."""
    _, cand, ctoken = _seed_recruiter_with_candidate(db_session)

    r = client.post(
        f"/api/v1/candidate/candidate/{cand.id}/proctoring",
        headers={"Authorization": f"Bearer {ctoken}"},
        json={
            "events": [
                {"event_type": "tab_switch"},
                {"event_type": "clipboard_paste", "details": {"note": "Ctrl+V"}},
                # Lifecycle events are dropped server-side.
                {"event_type": "monitoring_started"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["persisted"] is True
    assert body["count"] == 2

    rows = (
        db_session.query(ProctoringEvent)
        .filter(ProctoringEvent.candidate_id == cand.id)
        .all()
    )
    assert sorted(row.event_type for row in rows) == ["clipboard_paste", "tab_switch"]


def test_save_proctoring_requires_candidate_token(client, db_session):
    """No anonymous posts; the endpoint rejects missing tokens."""
    _, cand, _ = _seed_recruiter_with_candidate(db_session)

    r = client.post(
        f"/api/v1/candidate/candidate/{cand.id}/proctoring",
        json={"events": [{"event_type": "tab_switch"}]},
    )
    assert r.status_code in (401, 403)


def test_save_proctoring_rejects_token_for_other_candidate(client, db_session):
    """Candidate A's token cannot post events to candidate B's record."""
    _, cand_a, ctoken_a = _seed_recruiter_with_candidate(
        db_session, recruiter_email="ra@x.com"
    )
    _, cand_b, _ = _seed_recruiter_with_candidate(
        db_session, recruiter_email="rb@x.com"
    )

    r = client.post(
        f"/api/v1/candidate/candidate/{cand_b.id}/proctoring",
        headers={"Authorization": f"Bearer {ctoken_a}"},
        json={"events": [{"event_type": "tab_switch"}]},
    )
    assert r.status_code == 403


def test_proctoring_report_reads_from_event_table(client, db_session):
    """get_proctoring_report counts ProctoringEvent rows, not Answer.flag_reason."""
    rec, cand, _ = _seed_recruiter_with_candidate(db_session)

    # Seed events directly to skip the auth dance for this read-side test.
    for event_type in ["tab_switch", "tab_switch", "clipboard_paste"]:
        db_session.add(
            ProctoringEvent(candidate_id=cand.id, event_type=event_type)
        )
    db_session.commit()

    # Recruiter login → token.
    rtok = client.post(
        "/api/v1/auth/login",
        json={"email": rec.email, "password": "longpass1234"},
    ).json()["access_token"]

    r = client.post(
        f"/api/v1/candidate/candidate/{cand.id}/proctoring/report",
        headers={"Authorization": f"Bearer {rtok}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["event_counts"] == {"tab_switch": 2, "clipboard_paste": 1}
    # Risk-level field still present (kept for back-compat).
    assert body["risk_level"] in {"low", "medium", "high"}


def test_proctoring_report_rejects_other_recruiter(client, db_session):
    """Recruiter B can't read recruiter A's candidate's report."""
    rec_a, cand_a, _ = _seed_recruiter_with_candidate(
        db_session, recruiter_email="ra@x.com"
    )
    rec_b, _, _ = _seed_recruiter_with_candidate(
        db_session, recruiter_email="rb@x.com"
    )
    db_session.add(ProctoringEvent(candidate_id=cand_a.id, event_type="tab_switch"))
    db_session.commit()

    rtok_b = client.post(
        "/api/v1/auth/login",
        json={"email": rec_b.email, "password": "longpass1234"},
    ).json()["access_token"]

    r = client.post(
        f"/api/v1/candidate/candidate/{cand_a.id}/proctoring/report",
        headers={"Authorization": f"Bearer {rtok_b}"},
    )
    assert r.status_code in (403, 404)
