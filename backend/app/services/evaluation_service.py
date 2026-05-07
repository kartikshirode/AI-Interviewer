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
    ) -> Dict[str, Any]:
        """Evaluate a candidate's answer using Gemini.

        Scores the *content* of the answer only — not delivery. We
        deliberately do not ask the model to assess "confidence" or any
        other prosody-adjacent quality. Delivery scoring biases against
        accented speakers, neurodivergent candidates, and anxious
        candidates, has no defensible job-performance correlation, and
        sits at the centre of the ACLU v. Intuit/HireVue complaint.
        """

        system_prompt = f"""You are an expert technical interviewer evaluating a candidate's answer.
Evaluate the answer based on the substance of what was said:
1. Correctness (0-10): Is the technical content accurate?
2. Clarity (0-10): Is the explanation clear and well-structured?
3. Depth (0-10): Does the answer show good understanding of the topic?

Do NOT score how confident, fluent, assertive, or smooth the candidate sounds.
Do NOT penalise hesitations, fillers, accents, or non-native phrasing.
Score only the substance of what was said.

Compute an overall score (0-100) as the unweighted mean of correctness,
clarity, and depth multiplied by 10 (i.e. mean(0-10 scores) * 10).

Difficulty level: {difficulty}
{f"Topic: {topic}" if topic else ""}

Return ONLY a single JSON object with the keys:
{{
    "score": <overall score 0-100>,
    "correctness": <score 0-10>,
    "clarity": <score 0-10>,
    "depth": <score 0-10>,
    "feedback": "<detailed feedback on the answer>",
    "strengths": ["<strength 1>", "<strength 2>"],
    "areas_for_improvement": ["<area 1>", "<area 2>"]
}}

Do not wrap the JSON in markdown fences. Be strict but fair."""

        try:
            response = self.model.generate_content(
                f"{system_prompt}\n\nQuestion: {question}\n\nAnswer: {transcript}",
                generation_config={
                    "temperature": 0.3,
                    "max_output_tokens": 600,
                    "response_mime_type": "application/json",
                },
            )

            result = _extract_json(getattr(response, "text", "") or "")
            if not result:
                raise ValueError("Gemini returned non-JSON or empty content")

            return {
                "score": result.get("score", 50),
                "correctness": result.get("correctness", 5),
                "clarity": result.get("clarity", 5),
                "depth": result.get("depth", 5),
                "feedback": result.get("feedback", ""),
                "strengths": result.get("strengths", []),
                "areas_for_improvement": result.get("areas_for_improvement", []),
                "_ok": True,
            }
        except Exception as e:
            print(f"Error evaluating answer: {e}")
            return {
                "score": 50,
                "correctness": 5,
                "clarity": 5,
                "depth": 5,
                "feedback": "Evaluation failed",
                "strengths": [],
                "areas_for_improvement": [],
                "_ok": False,
                "_error": str(e),
            }

    def evaluate_communication(
        self, transcript: str, question_count: int = 1
    ) -> Dict[str, Any]:
        """Evaluate communication skills based on all transcripts."""

        system_prompt = """You are evaluating a candidate's communication skills during an interview.
Analyze their overall communication based on:
1. Clarity of expression (0-10)
2. Professionalism (0-10)
3. Conciseness (0-10)
4. Confidence indicator (0-10)

Return ONLY a single JSON object with the keys:
{
    "communication_score": <average 0-10>,
    "clarity": <score 0-10>,
    "professionalism": <score 0-10>,
    "conciseness": <score 0-10>,
    "confidence": <score 0-10>,
    "overall_feedback": "<overall communication feedback>"
}
Do not wrap the JSON in markdown fences."""

        try:
            response = self.model.generate_content(
                f"{system_prompt}\n\nCandidate's answers:\n\n{transcript}",
                generation_config={
                    "temperature": 0.3,
                    "max_output_tokens": 500,
                    "response_mime_type": "application/json",
                },
            )

            result = _extract_json(getattr(response, "text", "") or "")
            if not result:
                raise ValueError("Gemini returned non-JSON or empty content")

            return {
                "communication_score": result.get("communication_score", 7),
                "clarity": result.get("clarity", 7),
                "professionalism": result.get("professionalism", 7),
                "conciseness": result.get("conciseness", 7),
                "confidence": result.get("confidence", 7),
                "overall_feedback": result.get("overall_feedback", ""),
            }
        except Exception as e:
            print(f"Error evaluating communication: {e}")
            return {
                "communication_score": 7,
                "clarity": 7,
                "professionalism": 7,
                "conciseness": 7,
                "confidence": 7,
                "overall_feedback": "Communication evaluation failed",
            }

    def calculate_final_score(self, answers: list) -> Optional[Dict[str, Any]]:
        """Calculate final aggregated score from per-answer evaluations.

        The score is the unweighted mean of correctness/clarity/depth across
        all answers, scaled to 0-100. Delivery scoring (confidence, prosody)
        was removed in Phase 0.1. Returns None when there are no answers
        (callers must distinguish "no data" from a 0% score).
        """
        num_answers = len(answers) if answers else 0
        if num_answers == 0:
            return None

        total_correctness = sum(a.get("correctness", 5) for a in answers)
        total_clarity = sum(a.get("clarity", 5) for a in answers)
        total_depth = sum(a.get("depth", 5) for a in answers)

        final_score = (
            (total_correctness + total_clarity + total_depth) / (3 * num_answers) * 10
        )

        return {
            "final_score": round(final_score, 2),
            # `technical_score` retained as an alias for backward compatibility
            # with callers that still read it; same value as `final_score`
            # now that confidence/communication weighting is gone.
            "technical_score": round(final_score, 2),
            "total_questions": num_answers,
            "average_correctness": round(total_correctness / num_answers, 2),
            "average_clarity": round(total_clarity / num_answers, 2),
            "average_depth": round(total_depth / num_answers, 2),
        }


evaluation_service = EvaluationService()
