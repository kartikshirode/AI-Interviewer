"""ISSUE-6: cross-recruiter video access must be rejected."""

from app.models.models import Answer, Candidate, Interview, Recruiter


def _signup_login(client, email):
    client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "password123"}
    )
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    ).json()["access_token"]


def test_recruiter_b_cannot_read_recruiter_a_video(client, db_session, tmp_path):
    tok_a = _signup_login(client, "a@example.com")
    tok_b = _signup_login(client, "b@example.com")

    # Recruiter A creates an interview + candidate + answer + a fake video
    rec_a = db_session.query(Recruiter).filter_by(email="a@example.com").first()
    interview = Interview(
        recruiter_id=rec_a.id,
        role="Engineer",
        difficulty="medium",
        num_questions=1,
        interview_link="link-a",
        status="active",
    )
    db_session.add(interview)
    db_session.commit()
    cand = Candidate(interview_id=interview.id, name="C", email="c@example.com")
    db_session.add(cand)
    db_session.commit()

    fake_video = tmp_path / "v.webm"
    fake_video.write_bytes(b"\x00\x00\x00\x00")
    ans = Answer(
        candidate_id=cand.id,
        question_id=None,
        video_path=str(fake_video),
    )
    db_session.add(ans)
    db_session.commit()
    answer_id = ans.id

    # Recruiter A => can fetch
    r = client.get(
        f"/api/v1/videos/{answer_id}",
        headers={"Authorization": f"Bearer {tok_a}"},
    )
    assert r.status_code == 200

    # Recruiter B => 404 (does not leak existence)
    r = client.get(
        f"/api/v1/videos/{answer_id}",
        headers={"Authorization": f"Bearer {tok_b}"},
    )
    assert r.status_code == 404

    # Unauth => 401
    r = client.get(f"/api/v1/videos/{answer_id}")
    assert r.status_code == 401
