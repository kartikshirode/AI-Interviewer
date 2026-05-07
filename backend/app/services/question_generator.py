"""Pure Gemini-backed question generation, with a static-bank fallback.

Persistence and caching are now the caller's responsibility — the
QuestionBank table in the database is the system-of-record for previously
generated questions. This service only knows how to produce a fresh batch
when asked.

If `GEMINI_API_KEY` is unset OR the call raises, we degrade to the static
`fallback_provider` so the feature stays usable in dev / offline.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Callable, List, Optional

import google.generativeai as genai

logger = logging.getLogger(__name__)


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _extract_json_array(text: str) -> Optional[list]:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = _FENCE_RE.sub("", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, list) else None
    except json.JSONDecodeError:
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end > start:
            try:
                parsed = json.loads(cleaned[start : end + 1])
                return parsed if isinstance(parsed, list) else None
            except json.JSONDecodeError:
                return None
    return None


class QuestionGenerator:
    MAX_QUESTIONS = 20

    def __init__(self, fallback_provider: Callable[[str, str], List[str]]):
        api_key = os.getenv("GEMINI_API_KEY", "")
        if api_key:
            genai.configure(api_key=api_key)
            # `gemini-flash-latest` auto-tracks the current stable Flash model
            # so we don't break when older versions (e.g. 1.5-flash) are retired.
            self._model = genai.GenerativeModel("gemini-flash-latest")
        else:
            self._model = None
        self._fallback = fallback_provider

    # ── Public API ──────────────────────────────────────────────────────

    def generate(
        self,
        topic_name: str,
        difficulty: str,
        skills: Optional[List[str]] = None,
        count: int = 5,
    ) -> tuple[List[str], str]:
        """Return (questions, source) where source is "gemini" or "static".

        No caching — caller is expected to persist the result to the
        QuestionBank table so the next request can hit the DB directly.
        """
        count = max(1, min(int(count), self.MAX_QUESTIONS))
        topic_name = str(topic_name)
        difficulty = (difficulty or "medium").lower()
        skills = skills or []

        if self._model is not None:
            try:
                questions = self._call_gemini(topic_name, difficulty, skills, count)
                if questions:
                    return questions[:count], "gemini"
            except Exception:
                logger.exception(
                    "Gemini question generation failed for (%s, %s, skills=%s)",
                    topic_name,
                    difficulty,
                    skills,
                )

        # Fallback path — static bank doesn't know about skills.
        return list(self._fallback(topic_name, difficulty))[:count], "static"

    # ── Internals ───────────────────────────────────────────────────────

    def _call_gemini(
        self,
        topic_name: str,
        difficulty: str,
        skills: List[str],
        count: int,
    ) -> Optional[List[str]]:
        prompt = self._build_prompt(topic_name, difficulty, skills, count)
        response = self._model.generate_content(  # type: ignore[union-attr]
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )
        text = getattr(response, "text", None) or ""
        parsed = _extract_json_array(text)
        if not parsed:
            return None
        questions: List[str] = []
        for item in parsed:
            if isinstance(item, str):
                q = item.strip()
            elif isinstance(item, dict):
                q = str(item.get("question") or item.get("q") or "").strip()
            else:
                continue
            if q:
                questions.append(q)
        return questions or None

    @staticmethod
    def _build_prompt(
        topic_name: str, difficulty: str, skills: List[str], count: int
    ) -> str:
        difficulty_hint = {
            "easy": (
                "beginner-friendly, suitable for someone with under 1 year of "
                "experience. Focus on fundamentals and definitions."
            ),
            "medium": (
                "for an experienced practitioner with 2-4 years in the field. "
                "Mix conceptual depth with practical application."
            ),
            "hard": (
                "for a senior engineer / expert. Probe edge cases, tradeoffs, "
                "and deep architectural reasoning."
            ),
        }.get(difficulty.lower(), "for a mid-level practitioner.")

        skills_clause = ""
        if skills:
            joined = ", ".join(skills)
            skills_clause = (
                f"\n\nFocus particularly on these areas / sub-skills: {joined}. "
                f"Each question should test at least one of them."
            )

        return (
            f"You are designing a technical interview question bank for the topic "
            f"\"{topic_name}\" at the \"{difficulty}\" difficulty level "
            f"({difficulty_hint}).{skills_clause}\n\n"
            f"Generate exactly {count} distinct, well-formed interview questions. "
            f"Each question must be a single self-contained sentence or short "
            f"paragraph that an interviewer would actually ask. Do not number "
            f"them, do not prefix with 'Q:', do not include answers.\n\n"
            f"Return ONLY a JSON array of strings — no commentary, no markdown.\n"
            f"Example shape: [\"question one\", \"question two\"]"
        )
