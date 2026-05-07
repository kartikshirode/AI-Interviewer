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
    assert evaluation_service.calculate_final_score([]) is None
    assert evaluation_service.calculate_final_score(None) is None


def test_calculate_final_score_single_answer():
    """Phase 0.1: final_score = unweighted mean of correctness/clarity/depth
    × 10. No confidence / communication weighting anymore."""
    res = evaluation_service.calculate_final_score(
        [{"correctness": 8, "clarity": 9, "depth": 7}]
    )
    assert res is not None
    # mean(8, 9, 7) * 10 = 80
    assert res["final_score"] == 80.0
    # technical_score is kept as an alias of final_score for back-compat.
    assert res["technical_score"] == 80.0
    assert res["total_questions"] == 1


def test_calculate_final_score_no_confidence_in_output():
    """Phase 0.1 invariant: the result dict must not surface any
    confidence / communication / delivery field — those were removed."""
    res = evaluation_service.calculate_final_score(
        [{"correctness": 5, "clarity": 5, "depth": 5}]
    )
    assert res is not None
    forbidden = {"confidence", "confidence_score", "communication_score", "communication"}
    assert forbidden.isdisjoint(res.keys()), f"Leaked keys: {forbidden & res.keys()}"


# ── Phase 0.3 — percentile bands ──────────────────────────────────────────

from app.services.evaluation_service import compute_band, MIN_COHORT_SIZE


def test_compute_band_insufficient_cohort_returns_marker():
    """Below MIN_COHORT_SIZE, band must be 'insufficient_data' regardless
    of where the candidate's score falls."""
    res = compute_band(85.0, [85.0, 70.0, 60.0])
    assert res["band"] == "insufficient_data"
    assert res["cohort_size"] == 3
    assert res["percentile"] is None


def test_compute_band_top_30_with_clear_lead():
    """A candidate at the 90th percentile lands in top_30."""
    cohort = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95]
    assert len(cohort) >= MIN_COHORT_SIZE
    res = compute_band(95.0, cohort)
    assert res["band"] == "top_30"
    assert res["cohort_size"] == 10


def test_compute_band_bottom_30_with_clear_lag():
    cohort = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90]
    res = compute_band(5.0, cohort)
    assert res["band"] == "bottom_30"


def test_compute_band_middle_for_median_score():
    cohort = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    res = compute_band(50.0, cohort)
    assert res["band"] == "middle"


def test_compute_band_handles_none_score():
    """A candidate with no final_score should not blow up."""
    res = compute_band(None, [10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    assert res["band"] == "insufficient_data"
    assert res["percentile"] is None


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
