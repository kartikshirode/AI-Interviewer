"""Tests for the bank-first question resolver.

Stubs out the Gemini call so these run offline and stay deterministic — the
goal is to verify the bank-vs-Gemini decision logic, not Gemini itself.
"""

from __future__ import annotations

import itertools
from unittest.mock import patch

from app.models.models import QuestionBank, Topic
from app.routers.interviews import _persist_to_bank, _resolve_questions
from app.services.skills import normalize_skills_key


def _stub_generate(questions: list[str], with_rubric: bool = False):
    """Build a generator stub returning the Phase-1 tuple shape.

    The generator API now returns `[(question_text, rubric|None), ...]`.
    By default this stub passes `rubric=None` so the bank rows get the
    legacy fallback path; pass `with_rubric=True` to attach a synthetic
    valid rubric to each question for tests that need it.
    """
    counter = itertools.count(1)

    def _fn(self, topic_name, difficulty, skills=None, count=5):
        pairs = []
        for q in questions[:count]:
            text = f"{q} #{next(counter)}"
            rubric = (
                {
                    "key_concepts": ["concept-A", "concept-B"],
                    "anchors": {
                        "0": "no answer",
                        "1": "vague",
                        "2": "partial",
                        "3": "specific",
                        "4": "exemplary",
                    },
                }
                if with_rubric
                else None
            )
            pairs.append((text, rubric))
        return (pairs, "gemini")

    return _fn


def test_normalize_skills_key_is_stable():
    assert normalize_skills_key(None) == ""
    assert normalize_skills_key([]) == ""
    assert normalize_skills_key(["A", " a ", "B"]) == "a,b"
    assert normalize_skills_key(["c", "B", "a"]) == "a,b,c"


def test_first_call_invokes_gemini_and_persists(db_session):
    """Empty bank → generator is called → rows persisted with right key."""
    fake = _stub_generate(["q-alpha", "q-beta", "q-gamma"])
    with patch(
        "app.services.question_generator.QuestionGenerator.generate",
        new=fake,
    ):
        questions, source = _resolve_questions(
            db_session, "Python", "medium", ["asyncio"], count=3
        )

    assert source == "gemini"
    assert len(questions) == 3
    # Phase 1: each item is a (text, rubric_or_none) tuple.
    assert all(isinstance(item, tuple) and len(item) == 2 for item in questions)
    rows = db_session.query(QuestionBank).all()
    assert len(rows) == 3
    assert all(r.topic_name == "Python" for r in rows)
    assert all(r.difficulty == "medium" for r in rows)
    assert all(r.skills_key == "asyncio" for r in rows)
    assert all(r.times_used == 0 for r in rows)
    # Stub returned rubric=None → bank rows store None for the rubric.
    assert all(r.rubric_json is None for r in rows)


def test_second_call_serves_from_bank_without_gemini(db_session):
    """When bank has ≥ count matching rows, generator must not be called."""
    # Pre-seed the bank.
    for q in ["q1", "q2", "q3", "q4", "q5"]:
        db_session.add(
            QuestionBank(
                topic_name="Python",
                difficulty="medium",
                skills_key="asyncio",
                skills_json=["asyncio"],
                question_text=q,
                source="gemini",
            )
        )
    db_session.commit()

    sentinel = {"called": False}

    def _boom(self, *a, **kw):
        sentinel["called"] = True
        return ([("should-not-be-used", None)], "gemini")

    with patch(
        "app.services.question_generator.QuestionGenerator.generate",
        new=_boom,
    ):
        questions, source = _resolve_questions(
            db_session, "Python", "medium", ["asyncio"], count=3
        )

    assert sentinel["called"] is False
    assert source == "bank-hit"
    assert len(questions) == 3
    # Each item is now (text, rubric_or_none).
    texts = {text for text, _ in questions}
    assert texts.issubset({"q1", "q2", "q3", "q4", "q5"})
    # times_used must increment on the chosen rows.
    used = (
        db_session.query(QuestionBank)
        .filter(QuestionBank.times_used > 0)
        .count()
    )
    assert used == 3


def test_force_refresh_calls_gemini_even_with_full_bank(db_session):
    for q in ["q1", "q2", "q3", "q4", "q5"]:
        db_session.add(
            QuestionBank(
                topic_name="SQL",
                difficulty="hard",
                skills_key="",
                skills_json=[],
                question_text=q,
                source="gemini",
            )
        )
    db_session.commit()

    fake = _stub_generate(["fresh-1", "fresh-2"])
    with patch(
        "app.services.question_generator.QuestionGenerator.generate",
        new=fake,
    ):
        questions, source = _resolve_questions(
            db_session, "SQL", "hard", [], count=2, force_refresh=True
        )

    assert source == "gemini"
    assert len(questions) == 2
    # Old rows still there + new ones appended.
    total = db_session.query(QuestionBank).count()
    assert total == 7


def test_different_skills_create_separate_buckets(db_session):
    """Same topic+difficulty but different skills_key must not collide."""
    fake_a = _stub_generate(["a1", "a2", "a3"])
    with patch(
        "app.services.question_generator.QuestionGenerator.generate",
        new=fake_a,
    ):
        _resolve_questions(db_session, "Python", "medium", ["asyncio"], count=3)

    fake_b = _stub_generate(["b1", "b2", "b3"])
    with patch(
        "app.services.question_generator.QuestionGenerator.generate",
        new=fake_b,
    ):
        _resolve_questions(db_session, "Python", "medium", ["typing"], count=3)

    keys = sorted({r.skills_key for r in db_session.query(QuestionBank).all()})
    assert keys == ["asyncio", "typing"]


def test_persist_dedupes_on_unique_constraint(db_session):
    """Phase 1: _persist_to_bank now takes (text, rubric) tuples."""
    _persist_to_bank(
        db_session,
        topic_name="Rust",
        difficulty="easy",
        skills_key="tokio",
        skills_list=["tokio"],
        questions=[("Q1", None), ("Q2", None)],
        source="gemini",
    )
    # Re-insert the same set; unique constraint should swallow duplicates.
    _persist_to_bank(
        db_session,
        topic_name="Rust",
        difficulty="easy",
        skills_key="tokio",
        skills_list=["tokio"],
        questions=[("Q1", None), ("Q2", None), ("Q3", None)],
        source="gemini",
    )
    rows = db_session.query(QuestionBank).filter_by(topic_name="Rust").all()
    assert sorted(r.question_text for r in rows) == ["Q1", "Q2", "Q3"]


def test_general_skills_endpoint_returns_list(client):
    r = client.get("/api/v1/topics/general-skills")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert "Leadership" in body
    assert "Team management" in body


def test_topics_endpoint_includes_skills(client, db_session):
    """`Topic.skills` is exposed on the API response."""
    db_session.add(
        Topic(name="Python", description="...", skills=["asyncio", "typing"])
    )
    db_session.commit()
    r = client.get("/api/v1/topics/")
    assert r.status_code == 200
    body = r.json()
    python_row = next(t for t in body if t["name"] == "Python")
    assert python_row["skills"] == ["asyncio", "typing"]


def test_create_topic_persists_skills(client, db_session):
    # Need an authenticated recruiter
    client.post(
        "/api/v1/auth/signup",
        json={"email": "r@x.com", "password": "longpass1234"},
    )
    tok = client.post(
        "/api/v1/auth/login",
        json={"email": "r@x.com", "password": "longpass1234"},
    ).json()["access_token"]

    r = client.post(
        "/api/v1/topics/",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "name": "Rust",
            "description": "Memory-safe systems programming",
            "skills": ["tokio", "ownership", "error handling"],
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert sorted(body["skills"]) == ["error handling", "ownership", "tokio"]


def test_custom_topic_in_create_interview(client):
    """custom_topic generates and persists bank rows under that topic_name."""
    client.post(
        "/api/v1/auth/signup",
        json={"email": "r2@x.com", "password": "longpass1234"},
    )
    tok = client.post(
        "/api/v1/auth/login",
        json={"email": "r2@x.com", "password": "longpass1234"},
    ).json()["access_token"]

    fake = _stub_generate(["custom-q-1", "custom-q-2"])
    with patch(
        "app.services.question_generator.QuestionGenerator.generate",
        new=fake,
    ):
        r = client.post(
            "/api/v1/interviews/",
            headers={"Authorization": f"Bearer {tok}"},
            json={
                "role": "Backend Engineer",
                "difficulty": "medium",
                "num_questions": 2,
                "topics": [],
                "custom_topic": "Rust",
                "skills": ["tokio"],
            },
        )
    assert r.status_code == 201, r.text
    iv = r.json()
    # Questions should be attached to the interview from the custom topic.
    qs = client.get(
        f"/api/v1/interviews/{iv['id']}/questions",
        headers={"Authorization": f"Bearer {tok}"},
    ).json()
    assert len(qs) == 2
