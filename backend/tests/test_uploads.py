"""ISSUE-5: extension allowlist + size limit on candidate answer uploads."""

import io


def _setup_candidate_session(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "rec@example.com", "password": "password123"},
    )
    tok = client.post(
        "/api/v1/auth/login",
        json={"email": "rec@example.com", "password": "password123"},
    ).json()["access_token"]
    iv = client.post(
        "/api/v1/interviews/",
        json={
            "role": "Engineer",
            "difficulty": "medium",
            "num_questions": 1,
            "topics": [],
            "custom_questions": ["Tell me about yourself."],
        },
        headers={"Authorization": f"Bearer {tok}"},
    ).json()
    qs = client.get(
        f"/api/v1/interviews/{iv['id']}/questions",
        headers={"Authorization": f"Bearer {tok}"},
    ).json()
    question_id = qs[0]["id"]

    reg = client.post(
        f"/api/v1/candidate/interview/{iv['id']}/register",
        json={"name": "Cand", "email": "c@example.com"},
    ).json()

    return reg["id"], question_id, reg["session_token"]


def test_bad_audio_extension_rejected(client):
    cid, qid, sess = _setup_candidate_session(client)
    files = {"audio": ("evil.exe", io.BytesIO(b"MZ"), "audio/wav")}
    r = client.post(
        "/api/v1/candidate/answer",
        data={"candidate_id": cid, "question_id": qid, "transcript": "hello"},
        files=files,
        headers={"Authorization": f"Bearer {sess}"},
    )
    assert r.status_code == 400
    assert "extension" in r.json().get("detail", "").lower()


def test_bad_audio_mime_rejected(client):
    cid, qid, sess = _setup_candidate_session(client)
    # extension is allowed, but MIME is not
    files = {"audio": ("ok.wav", io.BytesIO(b"\x00" * 16), "application/x-msdownload")}
    r = client.post(
        "/api/v1/candidate/answer",
        data={"candidate_id": cid, "question_id": qid},
        files=files,
        headers={"Authorization": f"Bearer {sess}"},
    )
    assert r.status_code == 400


def test_oversized_upload_rejected_via_helper():
    """Pushing 50 MiB through TestClient is impractical, so we exercise the
    helper directly with an explicit small max_size. This verifies the
    streaming size-cap raises HTTP 413 when exceeded.

    NOTE: `_stream_upload_to_disk` binds `max_size = settings.MAX_UPLOAD_SIZE`
    as a function-default, which means `settings.MAX_UPLOAD_SIZE` cannot be
    overridden at runtime via monkeypatch. That's a code-quality regression
    worth flagging — see the regressions section of the test report.
    """
    import asyncio
    import io as _io
    from fastapi import HTTPException, UploadFile
    from app.routers.candidate import (
        _stream_upload_to_disk,
        ALLOWED_AUDIO_EXTS,
        ALLOWED_AUDIO_MIME_PREFIXES,
    )

    big = b"a" * 1024
    upload = UploadFile(filename="big.wav", file=_io.BytesIO(big))
    upload.headers.__dict__.setdefault("_list", [])  # noqa: SLF001
    # Force content-type
    upload.__dict__["headers"] = {"content-type": "audio/wav"}

    async def _go():
        return await _stream_upload_to_disk(
            upload,
            ALLOWED_AUDIO_EXTS,
            ALLOWED_AUDIO_MIME_PREFIXES,
            max_size=16,
        )

    try:
        asyncio.run(_go())
    except HTTPException as e:
        assert e.status_code == 413
    else:
        raise AssertionError("Expected HTTPException 413")


def test_valid_audio_accepted(client):
    cid, qid, sess = _setup_candidate_session(client)
    files = {"audio": ("ok.webm", io.BytesIO(b"\x00" * 32), "audio/webm")}
    r = client.post(
        "/api/v1/candidate/answer",
        data={"candidate_id": cid, "question_id": qid, "transcript": "hello"},
        files=files,
        headers={"Authorization": f"Bearer {sess}"},
    )
    assert r.status_code == 200, r.text
