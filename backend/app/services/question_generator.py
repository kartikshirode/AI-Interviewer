"""Dynamic question generation backed by Gemini.

Replaces the hardcoded SAMPLE_QUESTIONS bank with on-demand LLM-generated
questions, with two safety nets:

1. An in-process cache keyed by (topic_name, difficulty) so previewing
   doesn't hit the Gemini API every keystroke / topic toggle. Entries
   expire after CACHE_TTL_SECONDS or when explicitly invalidated.
2. A static fallback (`fallback_questions`) used when Gemini is unconfigured,
   rate-limited, or returns garbage. Callers always get something usable.

Thread-safe: the cache is guarded by a lock since FastAPI request handlers
may run concurrently in the threadpool.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Callable, List, Optional

import google.generativeai as genai

logger = logging.getLogger(__name__)


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _extract_json_array(text: str) -> Optional[list]:
    """Gemini sometimes wraps JSON in ```json ... ``` fences. Strip and parse.
    Returns None on failure."""
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
    CACHE_TTL_SECONDS = 30 * 60  # 30 min — long enough that preview→create reuses
    MAX_QUESTIONS = 10

    def __init__(self, fallback_provider: Callable[[str, str], List[str]]):
        api_key = os.getenv("GEMINI_API_KEY", "")
        if api_key:
            genai.configure(api_key=api_key)
            # `gemini-flash-latest` auto-tracks the current stable Flash model
            # so we don't break when older versions (e.g. 1.5-flash) are retired.
            self._model = genai.GenerativeModel("gemini-flash-latest")
        else:
            self._model = None
        self._cache: dict[tuple[str, str], tuple[float, List[str]]] = {}
        self._lock = threading.Lock()
        self._fallback = fallback_provider

    # ── Public API ──────────────────────────────────────────────────────

    def get_questions(
        self,
        topic_name: str,
        difficulty: str,
        count: int = 5,
        force_refresh: bool = False,
    ) -> List[str]:
        """Return up to `count` questions for the (topic, difficulty) pair.

        Cache hit → instant. Cache miss → call Gemini, cache the result.
        Any failure path falls back to the static bank. The list returned
        is always a fresh copy so callers can mutate it freely.
        """
        count = max(1, min(int(count), self.MAX_QUESTIONS))
        topic_name = str(topic_name)
        difficulty = (difficulty or "medium").lower()
        key = (topic_name, difficulty)

        if not force_refresh:
            cached = self._cache_get(key)
            if cached and len(cached) >= count:
                return list(cached[:count])

        questions: Optional[List[str]] = None
        if self._model is not None:
            try:
                questions = self._call_gemini(topic_name, difficulty, count)
            except Exception:
                logger.exception(
                    "Gemini question generation failed for (%s, %s)",
                    topic_name,
                    difficulty,
                )

        if not questions:
            questions = list(self._fallback(topic_name, difficulty))

        if questions:
            self._cache_set(key, questions)

        return list(questions[:count])

    def invalidate(self, topic_name: str, difficulty: str) -> None:
        with self._lock:
            self._cache.pop((str(topic_name), (difficulty or "medium").lower()), None)

    # ── Internals ───────────────────────────────────────────────────────

    def _cache_get(self, key: tuple[str, str]) -> Optional[List[str]]:
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            ts, value = entry
            if time.time() - ts > self.CACHE_TTL_SECONDS:
                self._cache.pop(key, None)
                return None
            return value

    def _cache_set(self, key: tuple[str, str], value: List[str]) -> None:
        with self._lock:
            self._cache[key] = (time.time(), list(value))

    def _call_gemini(
        self, topic_name: str, difficulty: str, count: int
    ) -> Optional[List[str]]:
        prompt = self._build_prompt(topic_name, difficulty, count)
        response = self._model.generate_content(  # type: ignore[union-attr]
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )
        text = getattr(response, "text", None) or ""
        parsed = _extract_json_array(text)
        if not parsed:
            return None
        # Accept either ["q1", "q2"] or [{"question": "q1"}, ...]
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
    def _build_prompt(topic_name: str, difficulty: str, count: int) -> str:
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

        return (
            f"You are designing a technical interview question bank for the topic "
            f"\"{topic_name}\" at the \"{difficulty}\" difficulty level "
            f"({difficulty_hint}).\n\n"
            f"Generate exactly {count} distinct, well-formed interview questions. "
            f"Each question must be a single self-contained sentence or short "
            f"paragraph that an interviewer would actually ask. Do not number "
            f"them, do not prefix with 'Q:', do not include answers.\n\n"
            f"Return ONLY a JSON array of strings — no commentary, no markdown.\n"
            f"Example shape: [\"question one\", \"question two\"]"
        )
