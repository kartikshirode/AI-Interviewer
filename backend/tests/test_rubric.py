"""Phase 1 tests — per-question rubric anchoring.

Pins down the new behaviour added by Phase 1.2-1.4:
- Generator parser tolerates old (string-only) and new ({question, rubric}) shapes.
- _resolve_questions round-trips rubrics from bank → caller.
- _persist_to_bank stores rubric_json alongside the question text.
- evaluate_answer rubric path returns rubric_score / justification / missing_concepts.
- evaluate_answer legacy path (no rubric) returns _legacy: True.
- force_refresh persists rubrics into the bank.
"""

from __future__ import annotations

from unittest.mock import patch

from app.models.models import QuestionBank
from app.routers.interviews import _persist_to_bank, _resolve_questions
from app.services.evaluation_service import evaluation_service
from app.services.question_generator import (
    QuestionGenerator,
    _validate_rubric,
    _extract_json_array,
)


VALID_RUBRIC = {
    "key_concepts": ["GIL serializes execution", "I/O vs CPU"],
    "anchors": {
        "0": "no answer",
        "1": "vague",
        "2": "partial",
        "3": "specific",
        "4": "exemplary",
    },
}


# ── Generator parser ──────────────────────────────────────────────────────


def test_validate_rubric_accepts_well_formed():
    res = _validate_rubric(VALID_RUBRIC)
    assert res is not None
    assert res["key_concepts"] == ["GIL serializes execution", "I/O vs CPU"]
    assert set(res["anchors"].keys()) == {"0", "1", "2", "3", "4"}


def test_validate_rubric_rejects_missing_anchor():
    bad = {**VALID_RUBRIC, "anchors": {"0": "a", "1": "b", "2": "c", "3": "d"}}
    assert _validate_rubric(bad) is None


def test_validate_rubric_rejects_empty_concepts():
    bad = {**VALID_RUBRIC, "key_concepts": []}
    assert _validate_rubric(bad) is None
    bad2 = {**VALID_RUBRIC, "key_concepts": ["", "  "]}
    assert _validate_rubric(bad2) is None


def test_generator_parser_tolerates_string_only_legacy_shape(monkeypatch):
    """Old-shape Gemini output (bare strings) must still flow through —
    rubric falls through as None."""
    gen = QuestionGenerator(fallback_provider=lambda t, d: ["fallback"])

    class FakeResponse:
        text = '["q1", "q2"]'

    class FakeModel:
        def generate_content(self, *_a, **_kw):
            return FakeResponse()

    gen._model = FakeModel()  # type: ignore[assignment]
    pairs, source = gen.generate("Python", "medium", count=2)
    assert source == "gemini"
    assert pairs == [("q1", None), ("q2", None)]


def test_generator_parser_passes_rubric_through(monkeypatch):
    gen = QuestionGenerator(fallback_provider=lambda t, d: [])

    class FakeResponse:
        text = (
            '[{"question": "explain GIL", "rubric": '
            '{"key_concepts": ["GIL"], '
            '"anchors": {"0": "no", "1": "v", "2": "p", "3": "s", "4": "e"}}}]'
        )

    class FakeModel:
        def generate_content(self, *_a, **_kw):
            return FakeResponse()

    gen._model = FakeModel()  # type: ignore[assignment]
    pairs, source = gen.generate("Python", "medium", count=1)
    assert source == "gemini"
    assert len(pairs) == 1
    text, rubric = pairs[0]
    assert text == "explain GIL"
    assert rubric is not None
    assert rubric["key_concepts"] == ["GIL"]


def test_generator_parser_drops_malformed_rubric_keeps_question(monkeypatch):
    gen = QuestionGenerator(fallback_provider=lambda t, d: [])

    class FakeResponse:
        text = (
            '[{"question": "still a good question", "rubric": '
            '{"key_concepts": ["X"], "anchors": {"0": "no"}}}]'
        )

    class FakeModel:
        def generate_content(self, *_a, **_kw):
            return FakeResponse()

    gen._model = FakeModel()  # type: ignore[assignment]
    pairs, _ = gen.generate("Python", "medium", count=1)
    assert pairs == [("still a good question", None)]


# ── Bank round-trip ────────────────────────────────────────────────────────


def test_persist_to_bank_stores_rubric(db_session):
    _persist_to_bank(
        db_session,
        topic_name="Python",
        difficulty="medium",
        skills_key="",
        skills_list=[],
        questions=[("q-with-rubric", VALID_RUBRIC)],
        source="gemini",
    )
    row = db_session.query(QuestionBank).filter_by(question_text="q-with-rubric").one()
    assert row.rubric_json == VALID_RUBRIC


def test_resolve_questions_round_trips_rubric_from_bank(db_session):
    """A bank-hit must surface the rubric persisted on the row."""
    for q in ["q1", "q2", "q3"]:
        db_session.add(
            QuestionBank(
                topic_name="Python",
                difficulty="medium",
                skills_key="",
                skills_json=[],
                question_text=q,
                rubric_json=VALID_RUBRIC,
                source="gemini",
            )
        )
    db_session.commit()

    pairs, source = _resolve_questions(
        db_session, "Python", "medium", [], count=3
    )
    assert source == "bank-hit"
    assert len(pairs) == 3
    for _text, rubric in pairs:
        assert rubric == VALID_RUBRIC


def test_force_refresh_persists_rubric_to_bank(db_session):
    """force_refresh → Gemini called → rubric saved on the new bank row."""
    def fake_generate(self, topic_name, difficulty, skills=None, count=5):
        return ([("fresh-q", VALID_RUBRIC)], "gemini")

    with patch(
        "app.services.question_generator.QuestionGenerator.generate",
        new=fake_generate,
    ):
        pairs, source = _resolve_questions(
            db_session,
            "Python",
            "medium",
            [],
            count=1,
            force_refresh=True,
        )

    assert source == "gemini"
    assert pairs == [("fresh-q", VALID_RUBRIC)]
    saved = db_session.query(QuestionBank).filter_by(question_text="fresh-q").one()
    assert saved.rubric_json == VALID_RUBRIC


# ── Evaluator branching ────────────────────────────────────────────────────


def test_evaluate_answer_uses_rubric_path_when_rubric_supplied(monkeypatch):
    """When the question has a rubric, the evaluator returns the
    Phase-1 shape (rubric_score / justification / missing_concepts) and
    NOT the legacy 0-10 trio."""

    class FakeResponse:
        text = (
            '{"rubric_score": 3, '
            '"justification": "candidate mentioned the GIL serializes execution", '
            '"missing_concepts": ["I/O vs CPU"]}'
        )

    def fake_generate(*_a, **_kw):
        return FakeResponse()

    monkeypatch.setattr(evaluation_service.model, "generate_content", fake_generate)

    res = evaluation_service.evaluate_answer(
        question="explain GIL",
        transcript="The GIL prevents two threads from running Python bytecode at once",
        rubric=VALID_RUBRIC,
    )
    assert res["_ok"] is True
    assert res["_legacy"] is False
    assert res["rubric_score"] == 3
    assert "GIL" in res["justification"]
    assert res["missing_concepts"] == ["I/O vs CPU"]


def test_evaluate_answer_falls_back_to_legacy_when_no_rubric(monkeypatch):
    """Legacy path: no rubric → generic prompt → _legacy=True. The trio
    of correctness/clarity/depth is still surfaced for back-compat
    display in the recruiter UI."""

    class FakeResponse:
        text = '{"correctness": 7, "clarity": 8, "depth": 6, "feedback": "ok"}'

    def fake_generate(*_a, **_kw):
        return FakeResponse()

    monkeypatch.setattr(evaluation_service.model, "generate_content", fake_generate)

    res = evaluation_service.evaluate_answer(
        question="explain GIL",
        transcript="something",
        rubric=None,
    )
    assert res["_ok"] is True
    assert res["_legacy"] is True
    # Legacy trio must come through.
    assert res["correctness"] == 7
    # Mean(7, 8, 6) / 2.5 = 7.0 / 2.5 = 2.8 → on 0-4 scale.
    assert res["rubric_score"] == 2.8


def test_evaluate_answer_rubric_path_rejects_out_of_range_score(monkeypatch):
    """A model that returns rubric_score=9 (out of 0-4) must end up as
    a failed eval, not a poisoned answer."""

    class FakeResponse:
        text = '{"rubric_score": 9, "justification": "x", "missing_concepts": []}'

    def fake_generate(*_a, **_kw):
        return FakeResponse()

    monkeypatch.setattr(evaluation_service.model, "generate_content", fake_generate)

    res = evaluation_service.evaluate_answer(
        question="q",
        transcript="a",
        rubric=VALID_RUBRIC,
    )
    assert res["_ok"] is False
    assert res["rubric_score"] is None


def test_extract_json_array_tolerates_fences():
    """Existing fence-tolerance must keep working with the new shape."""
    fenced = '```json\n[{"question": "q", "rubric": null}]\n```'
    res = _extract_json_array(fenced)
    assert res == [{"question": "q", "rubric": None}]
