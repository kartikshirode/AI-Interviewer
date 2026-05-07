import json
import os
import re
from typing import Any, Dict, Optional

import google.generativeai as genai


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


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
        """Evaluate a candidate's answer using Gemini."""

        system_prompt = f"""You are an expert technical interviewer evaluating a candidate's answer.
Evaluate the answer based on:
1. Correctness (0-10): Is the technical content accurate?
2. Clarity (0-10): Is the explanation clear and well-structured?
3. Depth (0-10): Does the answer show good understanding of the topic?
4. Confidence (0-10): Does the candidate sound confident and assertive?

Also compute an overall score (0-100) based on weighted combination:
- Technical accuracy (correctness + depth): 60%
- Communication (clarity): 25%
- Confidence: 15%

Difficulty level: {difficulty}
{f"Topic: {topic}" if topic else ""}

Return ONLY a single JSON object with the keys:
{{
    "score": <overall score 0-100>,
    "correctness": <score 0-10>,
    "clarity": <score 0-10>,
    "depth": <score 0-10>,
    "confidence": <score 0-10>,
    "technical_accuracy": <score 0-10>,
    "communication": <score 0-10>,
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
                "confidence": result.get("confidence", 5),
                "technical_accuracy": result.get("technical_accuracy", 5),
                "communication": result.get("communication", 5),
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
                "confidence": 5,
                "technical_accuracy": 5,
                "communication": 5,
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

    def calculate_final_score(
        self, answers: list, communication_score: float
    ) -> Optional[Dict[str, Any]]:
        """Calculate final aggregated score. Returns None when there are no
        answers (callers must distinguish "no data" from a 0% score)."""

        num_answers = len(answers) if answers else 0
        if num_answers == 0:
            return None

        total_correctness = sum(a.get("correctness", 5) for a in answers)
        total_clarity = sum(a.get("clarity", 5) for a in answers)
        total_depth = sum(a.get("depth", 5) for a in answers)

        technical_score = (
            (total_correctness + total_clarity + total_depth) / (3 * num_answers) * 10
        )
        final_score = (technical_score * 0.7) + (communication_score * 0.3)

        return {
            "technical_score": round(technical_score, 2),
            "communication_score": round(communication_score, 2),
            "final_score": round(final_score, 2),
            "total_questions": num_answers,
            "average_correctness": round(total_correctness / num_answers, 2),
            "average_clarity": round(total_clarity / num_answers, 2),
            "average_depth": round(total_depth / num_answers, 2),
        }


evaluation_service = EvaluationService()
