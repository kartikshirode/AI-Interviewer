"""Candidate registration / session token flow."""


def _make_recruiter_with_interview(client, email="r@example.com"):
    client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password123"},
    )
    tok = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    r = client.post(
        "/api/v1/interviews/",
        json={
            "role": "Backend Engineer",
            "difficulty": "medium",
            "num_questions": 3,
            "topics": [],
            "custom_questions": ["Q1?", "Q2?", "Q3?"],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return tok, r.json()


def test_register_returns_session_token(client):
    _, interview = _make_recruiter_with_interview(client)
    r = client.post(
        f"/api/v1/candidate/interview/{interview['id']}/register",
        json={"name": "Bob", "email": "bob@example.com"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "session_token" in body and body["session_token"]
    assert body["interview_id"] == interview["id"]


def test_submit_answer_requires_candidate_token(client):
    """ISSUE-4: submitting an answer without the candidate session token must
    be rejected."""
    _, interview = _make_recruiter_with_interview(client)
    reg = client.post(
        f"/api/v1/candidate/interview/{interview['id']}/register",
        json={"name": "Bob", "email": "bob@example.com"},
    ).json()

    # No Authorization header => 401
    r = client.post(
        "/api/v1/candidate/answer",
        data={"candidate_id": reg["id"], "question_id": 1},
    )
    assert r.status_code == 401

    # Garbage Bearer token => 401
    r = client.post(
        "/api/v1/candidate/answer",
        data={"candidate_id": reg["id"], "question_id": 1},
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert r.status_code == 401

    # Recruiter token is also not valid as a candidate token — wrong scope.
    rec_email = "rec2@example.com"
    client.post(
        "/api/v1/auth/signup",
        json={"email": rec_email, "password": "password123"},
    )
    rec_tok = client.post(
        "/api/v1/auth/login",
        json={"email": rec_email, "password": "password123"},
    ).json()["access_token"]
    r = client.post(
        "/api/v1/candidate/answer",
        data={"candidate_id": reg["id"], "question_id": 1},
        headers={"Authorization": f"Bearer {rec_tok}"},
    )
    assert r.status_code == 401


def test_candidate_token_only_valid_for_its_interview(client):
    _, interview = _make_recruiter_with_interview(client)
    reg = client.post(
        f"/api/v1/candidate/interview/{interview['id']}/register",
        json={"name": "Bob", "email": "bob@example.com"},
    ).json()

    headers = {"Authorization": f"Bearer {reg['session_token']}"}
    # Fetch questions for the right interview => 200
    r = client.get(
        f"/api/v1/candidate/interview/{interview['id']}/questions", headers=headers
    )
    assert r.status_code == 200

    # Different interview id => 403 token/interview mismatch
    r = client.get(
        f"/api/v1/candidate/interview/{interview['id'] + 999}/questions",
        headers=headers,
    )
    assert r.status_code in (403, 404)
