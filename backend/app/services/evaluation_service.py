import json
import os
import re
from typing import Any, Dict, Optional

import google.generativeai as genai


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


# Phase 0.3: percentile-band thresholds. Anything in the top 30% of a
# (role, difficulty) cohort lands in `top_30`; the bottom 30% in
# `bottom_30`; the rest in `middle`. Below `MIN_COHORT_SIZE` we don't
# emit a band at all — the percentile would be too noisy to defend.
TOP_THRESHOLD = 0.70
BOTTOM_THRESHOLD = 0.30
MIN_COHORT_SIZE = 10


def compute_band(candidate_score: Optional[float], cohort_scores: list[float]) -> Dict[str, Any]:
    """Place `candidate_score` into a percentile band against `cohort_scores`.

    `cohort_scores` should already include the candidate's own score —
    we use a rank-based percentile (`below + 0.5 * equal) / n`) so a
    single-element cohort containing only the candidate himself lands at
    50% rather than 0% or 100%. Both the band and the cohort size are
    returned so the recruiter UI can disclose how many candidates the
    band is computed against.

    Returns:
      `{band: "top_30" | "middle" | "bottom_30" | "insufficient_data",
        cohort_size: int, percentile: float | None}`
    """
    if candidate_score is None:
        return {"band": "insufficient_data", "cohort_size": 0, "percentile": None}

    n = len(cohort_scores)
    if n < MIN_COHORT_SIZE:
        return {"band": "insufficient_data", "cohort_size": n, "percentile": None}

    below = sum(1 for s in cohort_scores if s < candidate_score)
    equal = sum(1 for s in cohort_scores if s == candidate_score)
    percentile = (below + 0.5 * equal) / n

    if percentile >= TOP_THRESHOLD:
        band = "top_30"
    elif percentile <= BOTTOM_THRESHOLD:
        band = "bottom_30"
    else:
        band = "middle"

    return {"band": band, "cohort_size": n, "percentile": round(percentile, 3)}


def _extract_json(text: str) -> Optional[dict]:
    """Gemini sometimes wraps JSON in ```json ... ``` fences. Strip them and
    parse. Returns None on failure."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = _FENCE_RE.sub("", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Last-ditch: extract the first {...} block.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


class EvaluationService:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
        # `gemini-flash-latest` auto-tracks the current stable Flash model.
        # The previous pin to gemini-1.5-flash silently 404'd after Google
        # retired it, which made every evaluation fall through to the
        # error path and persist no scores.
        self.model = genai.GenerativeModel("gemini-flash-latest")

    def evaluate_answer(
        self,
        question: str,
        transcript: str,
        difficulty: str = "medium",
        topic: Optional[str] = None,
        rubric: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Evaluate a candidate's answer.

        Phase 1: when a per-question rubric is supplied, the evaluator
        anchors the score against that rubric (`rubric_score: 0-4`).
        Per-question rubrics raise LLM-grader agreement with humans from
        ICC ≈ 0.56 to ≈ 0.82. When no rubric is supplied (legacy
        questions generated before Phase 1), we fall back to the generic
        prompt and return `_legacy: True` so the recruiter UI can flag
        the lower-confidence path.

        Scores the *content* of the answer only — never delivery. The
        rubric anchors are about substance ("explains the GIL serializes
        execution"), not about how smoothly the candidate sounded.
        """
        if rubric is not None:
            return self._evaluate_with_rubric(
                question, transcript, rubric, difficulty=difficulty, topic=topic
            )
        return self._evaluate_legacy(
            question, transcript, difficulty=difficulty, topic=topic
        )

    def _evaluate_with_rubric(
        self,
        question: str,
        transcript: str,
        rubric: dict,
        difficulty: str,
        topic: Optional[str],
    ) -> Dict[str, Any]:
        # Pretty-print the anchors so the model sees one labeled line per
        # level — that maximises the chance it picks a specific anchor
        # rather than averaging.
        anchors = rubric.get("anchors", {})
        key_concepts = rubric.get("key_concepts", [])
        anchor_block = "\n".join(
            f"  {level}: {anchors.get(str(level), '').strip()}" for level in (0, 1, 2, 3, 4)
        )
        concepts_block = "\n".join(f"  - {c}" for c in key_concepts)

        topic_line = f"Topic: {topic}\n" if topic else ""

        system_prompt = f"""You are an interviewer scoring a single candidate answer against a rubric anchored to this specific question. Score the substance of what was said. Do NOT score delivery, fluency, accent, hesitation, or confidence.

Question: {question}
Difficulty: {difficulty}
{topic_line}
Key concepts an excellent answer must address:
{concepts_block}

Score anchors (pick the level whose description best fits the answer):
{anchor_block}

Pick exactly one of {{0, 1, 2, 3, 4}} as `rubric_score`. Quote or paraphrase a specific phrase from the candidate's answer in `justification` to ground the score (one sentence). In `missing_concepts`, list the key concepts above that the candidate did NOT address (verbatim from the list, or empty list if all addressed).

Return ONLY this JSON object — no markdown fences, no commentary:
{{
  "rubric_score": <0|1|2|3|4>,
  "justification": "<one sentence anchoring the score>",
  "missing_concepts": ["<concept verbatim>", ...]
}}"""

        try:
            response = self.model.generate_content(
                f"{system_prompt}\n\nCandidate's answer:\n{transcript}",
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 400,
                    "response_mime_type": "application/json",
                },
            )

            result = _extract_json(getattr(response, "text", "") or "")
            if not result:
                raise ValueError("Gemini returned non-JSON or empty content")

            score_raw = result.get("rubric_score")
            try:
                score = int(score_raw)
            except (TypeError, ValueError):
                raise ValueError(f"rubric_score not an int: {score_raw!r}")
            if score not in (0, 1, 2, 3, 4):
                raise ValueError(f"rubric_score out of range: {score}")

            justification = str(result.get("justification") or "").strip()
            raw_missing = result.get("missing_concepts") or []
            if isinstance(raw_missing, list):
                missing = [str(c).strip() for c in raw_missing if str(c).strip()]
            else:
                missing = []

            return {
                "rubric_score": score,
                "justification": justification,
                "missing_concepts": missing,
                "_legacy": False,
                "_ok": True,
            }
        except Exception as e:
            print(f"Error evaluating answer (rubric path): {e}")
            return {
                "rubric_score": None,
                "justification": "",
                "missing_concepts": [],
                "_legacy": False,
                "_ok": False,
                "_error": str(e),
            }

    def _evaluate_legacy(
        self,
        question: str,
        transcript: str,
        difficulty: str,
        topic: Optional[str],
    ) -> Dict[str, Any]:
        """Pre-Phase-1 generic evaluation. Used when a question has no
        per-question rubric (e.g. it was generated before Phase 1, or the
        static fallback bank surfaced it). The recruiter UI flags these
        as lower-confidence so they're easy to triage.
        """
        system_prompt = f"""You are an expert technical interviewer evaluating a candidate's answer.
Evaluate the answer based on the substance of what was said:
1. Correctness (0-10): Is the technical content accurate?
2. Clarity (0-10): Is the explanation clear and well-structured?
3. Depth (0-10): Does the answer show good understanding of the topic?

Do NOT score delivery, fluency, accent, hesitation, or confidence.

Difficulty level: {difficulty}
{f"Topic: {topic}" if topic else ""}

Return ONLY a single JSON object with the keys:
{{
    "correctness": <score 0-10>,
    "clarity": <score 0-10>,
    "depth": <score 0-10>,
    "feedback": "<one-sentence feedback>"
}}
Do not wrap the JSON in markdown fences."""

        try:
            response = self.model.generate_content(
                f"{system_prompt}\n\nQuestion: {question}\n\nAnswer: {transcript}",
                generation_config={
                    "temperature": 0.3,
                    "max_output_tokens": 400,
                    "response_mime_type": "application/json",
                },
            )

            result = _extract_json(getattr(response, "text", "") or "")
            if not result:
                raise ValueError("Gemini returned non-JSON or empty content")

            # Map the 0-10 trio to a 0-4 rubric_score so the report's
            # aggregator has a single column to average. Mean of
            # correctness/clarity/depth, then divide by 2.5 (10 → 4).
            try:
                trio = (
                    float(result.get("correctness", 5)),
                    float(result.get("clarity", 5)),
                    float(result.get("depth", 5)),
                )
            except (TypeError, ValueError):
                trio = (5.0, 5.0, 5.0)
            rubric_score_equiv = round(sum(trio) / 3 / 2.5, 2)

            return {
                "rubric_score": rubric_score_equiv,
                "justification": str(result.get("feedback") or "").strip(),
                "missing_concepts": [],
                # Legacy debugging fields — recruiter UI may show them
                # under a "raw scores" disclosure for legacy answers.
                "correctness": trio[0],
                "clarity": trio[1],
                "depth": trio[2],
                "_legacy": True,
                "_ok": True,
            }
        except Exception as e:
            print(f"Error evaluating answer (legacy path): {e}")
            return {
                "rubric_score": None,
                "justification": "",
                "missing_concepts": [],
                "_legacy": True,
                "_ok": False,
                "_error": str(e),
            }

    def calculate_final_score(self, answers: list) -> Optional[Dict[str, Any]]:
        """Calculate final aggregated score from per-answer evaluations.

        Phase 1: score is the mean of `rubric_score` (each on 0-4) across
        all answers, scaled to 0-100 by ×25. Returns None when there are
        no answers — callers must distinguish "no data" from a 0% score.
        Answers without a `rubric_score` (e.g. failed evaluation) are
        skipped — they do not pull the mean down.
        """
        if not answers:
            return None
        rubric_scores = [
            float(a["rubric_score"])
            for a in answers
            if a.get("rubric_score") is not None
        ]
        if not rubric_scores:
            return None

        n = len(rubric_scores)
        mean_rubric = sum(rubric_scores) / n
        final_score = mean_rubric * 25  # 0-4 → 0-100

        return {
            "final_score": round(final_score, 2),
            # `technical_score` retained as an alias for back-compat with
            # callers that still read it.
            "technical_score": round(final_score, 2),
            "mean_rubric_score": round(mean_rubric, 2),
            "total_questions": n,
        }


evaluation_service = EvaluationService()
