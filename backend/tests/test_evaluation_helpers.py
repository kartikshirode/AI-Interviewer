"""Pure-Python helpers from evaluation_service / interviews routers.

These tests do not hit Gemini.
"""

from app.services.evaluation_service import _extract_json, evaluation_service
from app.routers.interviews import _distribute_question_count


def test_extract_json_strips_markdown_fences():
    """ISSUE-12: Gemini occasionally wraps JSON in ```json ... ``` fences."""
    raw = '```json\n{"correctness": 8, "feedback": "ok"}\n```'
    parsed = _extract_json(raw)
    assert parsed == {"correctness": 8, "feedback": "ok"}


def test_extract_json_strips_plain_fences():
    raw = '```\n{"a": 1}\n```'
    assert _extract_json(raw) == {"a": 1}


def test_extract_json_falls_back_to_brace_extraction():
    raw = "Here's the result: {\"score\": 42} -- end"
    assert _extract_json(raw) == {"score": 42}


def test_extract_json_returns_none_on_garbage():
    assert _extract_json("not json at all") is None
    assert _extract_json("") is None
    assert _extract_json(None) is None


def test_calculate_final_score_empty_returns_none():
    """ISSUE-30: empty answers must return None, not score 0."""
    assert evaluation_service.calculate_final_score([], 7.5) is None
    assert evaluation_service.calculate_final_score(None, 7.5) is None


def test_calculate_final_score_single_answer():
    res = evaluation_service.calculate_final_score(
        [{"correctness": 8, "clarity": 9, "depth": 7}], 8.0
    )
    assert res is not None
    # technical = (8+9+7) / 3 * 10 / 1 = 80
    assert res["technical_score"] == 80.0
    # final = 80*0.7 + 8*0.3 = 56 + 2.4 = 58.4
    assert res["final_score"] == 58.4
    assert res["total_questions"] == 1


def test_distribute_question_count_three_topics_total_five():
    """ISSUE-18: 3 topics x num_questions=5 must total 5, not 15."""
    counts = _distribute_question_count(5, 3)
    assert sum(counts) == 5
    assert len(counts) == 3
    # earlier buckets get the +1 remainder
    assert counts == [2, 2, 1]


def test_distribute_question_count_edge_cases():
    assert _distribute_question_count(0, 3) == []
    assert _distribute_question_count(5, 0) == []
    assert _distribute_question_count(10, 5) == [2, 2, 2, 2, 2]
    assert _distribute_question_count(7, 3) == [3, 2, 2]
