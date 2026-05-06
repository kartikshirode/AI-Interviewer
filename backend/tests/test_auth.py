"""Auth flow + recruiter-protected endpoint smoke tests."""


def _signup_and_login(client, email="alice@example.com", password="password123"):
    r = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "full_name": "Alice", "company": "Acme"},
    )
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_signup_then_login_then_authorized_list(client):
    token = _signup_and_login(client)
    # No token => 401 (Not authenticated)
    r = client.get("/api/v1/interviews/")
    assert r.status_code == 401

    # Bad token => 401
    r = client.get(
        "/api/v1/interviews/", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert r.status_code == 401

    # Good token => 200, empty list
    r = client.get(
        "/api/v1/interviews/", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    assert r.json() == []


def test_login_unknown_user_and_wrong_password_same_shape(client):
    """ISSUE-38: timing-safe login should give an indistinguishable response
    shape for a user that doesn't exist vs. a wrong password."""
    # Register one user
    client.post(
        "/api/v1/auth/signup",
        json={
            "email": "real@example.com",
            "password": "correctpassword",
            "full_name": "R",
            "company": "C",
        },
    )

    r1 = client.post(
        "/api/v1/auth/login",
        json={"email": "real@example.com", "password": "WRONGpassword"},
    )
    r2 = client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "anyOldPass1"},
    )
    assert r1.status_code == 401
    assert r2.status_code == 401
    assert r1.json() == r2.json()  # identical detail body


def test_signup_duplicate_email_rejected(client):
    body = {"email": "dup@example.com", "password": "password123"}
    r = client.post("/api/v1/auth/signup", json=body)
    assert r.status_code == 201
    r = client.post("/api/v1/auth/signup", json=body)
    assert r.status_code == 400


def test_signup_short_password_rejected(client):
    r = client.post(
        "/api/v1/auth/signup", json={"email": "x@x.com", "password": "short"}
    )
    assert r.status_code == 422
