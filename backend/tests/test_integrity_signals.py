"""Phase 2.1 + 2.3 + 2.5 — integrity signals.

Pins:
- transcript_features extracts plausible counts on synthetic inputs
- Answer.first_word_ms / started_at / transcript_features land via submit
- get_candidate_report integrity panel surfaces latency + features +
  proctoring counts and never invents a single 'cheat probability' field
"""

from __future__ import annotations

import io

from app.services.transcript_features import (
    extract_features,
    sentence_length_variance,
    structural_marker_count,
    word_count,
)


# ── Pure helper tests ─────────────────────────────────────────────────────


def test_word_count_handles_empty_and_none():
    assert word_count(None) == 0
    assert word_count("") == 0
    assert word_count("   ") == 0
    assert word_count("hello world") == 2


def test_word_count_handles_punctuation_and_apostrophes():
    assert word_count("It's a test, isn't it?") == 5


def test_sentence_length_variance_zero_for_short_inputs():
    assert sentence_length_variance(None) == 0.0
    assert sentence_length_variance("") == 0.0
    assert sentence_length_variance("just one sentence") == 0.0


def test_sentence_length_variance_positive_for_uneven_sentences():
    """Two sentences of different word counts → positive variance."""
    res = sentence_length_variance("Short. This is a longer sentence with more words.")
    assert res > 0


def test_structural_marker_count_picks_up_discourse_markers():
    text = "Firstly we plan. Secondly we build. In conclusion we ship."
    assert structural_marker_count(text) == 3


def test_structural_marker_count_picks_up_numbered_lists():
    text = "1. First item\n2. Second item\n3. Third item"
    assert structural_marker_count(text) >= 3


def test_extract_features_bundle_shape():
    res = extract_features("Firstly we ship. Then we iterate.")
    assert set(res.keys()) == {
        "word_count",
        "sentence_length_variance",
        "structural_marker_count",
    }
    assert res["word_count"] == 6
    assert res["structural_marker_count"] == 1


# ── End-to-end via the API ────────────────────────────────────────────────


def _seed_through_api(client):
    """Boilerplate: create a recruiter, an interview, register a candidate,
    return (recruiter_token, candidate_id, candidate_token, question_id)."""
    client.post(
        "/api/v1/auth/signup",
        json={"email": "rint@x.com", "password": "longpass1234"},
    )
    rtok = client.post(
        "/api/v1/auth/login",
        json={"email": "rint@x.com", "password": "longpass1234"},
    ).json()["access_token"]

    iv = client.post(
        "/api/v1/interviews/",
        headers={"Authorization": f"Bearer {rtok}"},
        json={
            "role": "SWE",
            "difficulty": "medium",
            "num_questions": 1,
            "topics": [],
            "custom_topic": None,
            "custom_questions": ["What is the GIL?"],
            "skills": [],
        },
    ).json()
    iv_id = iv["id"]

    qs = client.get(
        f"/api/v1/interviews/{iv_id}/questions",
        headers={"Authorization": f"Bearer {rtok}"},
    ).json()
    question_id = qs[0]["id"]

    body = client.post(
        f"/api/v1/candidate/interview/{iv_id}/register",
        json={"name": "C", "email": "cint@x.com"},
    ).json()
    return rtok, body["id"], body["session_token"], question_id


def test_submit_answer_persists_latency_and_features(client, db_session):
    from app.models.models import Answer

    _rtok, cand_id, ctok, qid = _seed_through_api(client)

    r = client.post(
        "/api/v1/candidate/answer",
        headers={"Authorization": f"Bearer {ctok}"},
        data={
            "candidate_id": cand_id,
            "question_id": qid,
            "transcript": "Firstly the GIL serializes execution. Secondly it matters for CPU bound code.",
            "started_at_ms": 1_700_000_000_000,
            "first_word_ms": 1450,
        },
    )
    assert r.status_code == 200, r.text

    db_session.expire_all()
    saved = db_session.query(Answer).filter(Answer.candidate_id == cand_id).one()
    assert saved.first_word_ms == 1450
    assert saved.started_at is not None
    assert saved.transcript_features is not None
    assert saved.transcript_features["word_count"] == 12
    assert saved.transcript_features["structural_marker_count"] == 2


def test_submit_answer_without_timing_is_still_accepted(client, db_session):
    from app.models.models import Answer

    _rtok, cand_id, ctok, qid = _seed_through_api(client)

    r = client.post(
        "/api/v1/candidate/answer",
        headers={"Authorization": f"Bearer {ctok}"},
        data={
            "candidate_id": cand_id,
            "question_id": qid,
            "transcript": "hi",
        },
    )
    assert r.status_code == 200

    db_session.expire_all()
    saved = db_session.query(Answer).filter(Answer.candidate_id == cand_id).one()
    assert saved.first_word_ms is None
    assert saved.started_at is None
    # Features still computed even without timing.
    assert saved.transcript_features == {
        "word_count": 1,
        "sentence_length_variance": 0.0,
        "structural_marker_count": 0,
    }


def test_candidate_report_exposes_integrity_panel(client, db_session):
    from app.models.models import Answer, ProctoringEvent

    rtok, cand_id, ctok, qid = _seed_through_api(client)

    # Submit a couple of answers with different latencies.
    for fw, transcript in [(1500, "GIL serializes execution."), (1450, "CPU-bound suffers more.")]:
        client.post(
            "/api/v1/candidate/answer",
            headers={"Authorization": f"Bearer {ctok}"},
            data={
                "candidate_id": cand_id,
                "question_id": qid,
                "transcript": transcript,
                "started_at_ms": 1_700_000_000_000,
                "first_word_ms": fw,
            },
        )
    # Seed a couple of proctoring events directly via the DB so we don't
    # need to drive the batched flush logic in this test.
    for et in ["tab_switch", "tab_switch", "clipboard_paste"]:
        db_session.add(ProctoringEvent(candidate_id=cand_id, event_type=et))
    db_session.commit()

    r = client.get(
        f"/api/v1/candidate/candidate/{cand_id}/report",
        headers={"Authorization": f"Bearer {rtok}"},
    )
    assert r.status_code == 200
    body = r.json()
    integrity = body["integrity"]
    # The panel must NOT surface a single "cheat probability" / similar.
    forbidden = {"cheat_probability", "cheating_probability", "fraud_score"}
    assert forbidden.isdisjoint(integrity.keys())
    # Latency surface
    assert integrity["first_word_ms"]["count"] == 1  # answers dedupe on (cand,q)
    assert integrity["first_word_ms"]["values"]
    # Transcript feature totals
    assert integrity["transcript_features"]["word_count_total"] >= 1
    # Proctoring counts come straight from the persisted events.
    assert integrity["proctoring_counts"]["tab_switch"] == 2
    assert integrity["proctoring_counts"]["clipboard_paste"] == 1
