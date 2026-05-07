"""Pure Gemini-backed question generation, with a static-bank fallback.

Persistence and caching are now the caller's responsibility — the
QuestionBank table in the database is the system-of-record for previously
generated questions. This service only knows how to produce a fresh batch
when asked.

Phase 1: each generated question now ships with a per-question rubric
(`{key_concepts: [...], anchors: {"0": ..., "4": ...}}`). Per-question
rubrics raise LLM-grader agreement with humans from ICC ~0.56 to ~0.82
(Pathak et al. ICER 2025) — the single biggest scoring quality win
available. Generation cost is unchanged because the rubric comes back in
the same Gemini call as the question.

If `GEMINI_API_KEY` is unset OR the call raises, we degrade to the static
`fallback_provider` so the feature stays usable in dev / offline. Static
fallback returns rubrics as `None`; the evaluator handles that case via
its legacy generic-prompt path.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, List, Optional, Tuple

import google.generativeai as genai

logger = logging.getLogger(__name__)


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


# A `(question_text, rubric | None)` pair returned to the caller. The
# resolver and bank persistence code use this same shape.
QuestionWithRubric = Tuple[str, Optional[dict]]


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


# ── Rubric validation ──────────────────────────────────────────────────────


_REQUIRED_ANCHOR_KEYS = {"0", "1", "2", "3", "4"}


def _validate_rubric(rubric: Any) -> Optional[dict]:
    """Strictly validate the per-question rubric shape Gemini returns.

    Returns the normalized rubric on success, or `None` on any malformation
    so the caller treats the question as legacy. We never reject the
    question itself — a missing rubric is the legacy fallback path, not a
    fatal error.

    Required shape:
      {
        "key_concepts": [<non-empty str>, ...],   # at least one
        "anchors": {
          "0": <non-empty str>,
          "1": <non-empty str>,
          "2": <non-empty str>,
          "3": <non-empty str>,
          "4": <non-empty str>,
        }
      }
    """
    if not isinstance(rubric, dict):
        return None
    key_concepts = rubric.get("key_concepts")
    anchors = rubric.get("anchors")
    if not isinstance(key_concepts, list) or not key_concepts:
        return None
    cleaned_concepts = [str(c).strip() for c in key_concepts if isinstance(c, str) and str(c).strip()]
    if not cleaned_concepts:
        return None
    if not isinstance(anchors, dict):
        return None
    if set(map(str, anchors.keys())) != _REQUIRED_ANCHOR_KEYS:
        return None
    cleaned_anchors: dict[str, str] = {}
    for k in _REQUIRED_ANCHOR_KEYS:
        val = anchors.get(k) or anchors.get(int(k)) if hasattr(anchors, "get") else None
        if not isinstance(val, str) or not val.strip():
            return None
        cleaned_anchors[k] = val.strip()
    return {"key_concepts": cleaned_concepts, "anchors": cleaned_anchors}


# ──────────────────────────────────────────────────────────────────────────


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
    ) -> tuple[List[QuestionWithRubric], str]:
        """Return (questions_with_rubrics, source) where source is
        "gemini" or "static".

        Each item is a `(question_text, rubric_or_none)` tuple. Static
        fallback never includes rubrics (we don't author them by hand);
        the evaluator handles the legacy path. No caching — caller is
        expected to persist the result to the QuestionBank table.
        """
        count = max(1, min(int(count), self.MAX_QUESTIONS))
        topic_name = str(topic_name)
        difficulty = (difficulty or "medium").lower()
        skills = skills or []

        if self._model is not None:
            try:
                pairs = self._call_gemini(topic_name, difficulty, skills, count)
                if pairs:
                    return pairs[:count], "gemini"
            except Exception:
                logger.exception(
                    "Gemini question generation failed for (%s, %s, skills=%s)",
                    topic_name,
                    difficulty,
                    skills,
                )

        # Fallback path — static bank doesn't carry rubrics.
        static_questions = list(self._fallback(topic_name, difficulty))[:count]
        return [(q, None) for q in static_questions], "static"

    # ── Internals ───────────────────────────────────────────────────────

    def _call_gemini(
        self,
        topic_name: str,
        difficulty: str,
        skills: List[str],
        count: int,
    ) -> Optional[List[QuestionWithRubric]]:
        prompt = self._build_prompt(topic_name, difficulty, skills, count)
        response = self._model.generate_content(  # type: ignore[union-attr]
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )
        text = getattr(response, "text", None) or ""
        parsed = _extract_json_array(text)
        if not parsed:
            return None

        pairs: List[QuestionWithRubric] = []
        for item in parsed:
            # Phase 1 shape: {"question": str, "rubric": {...}}.
            # Pre-Phase-1 / fallback shape: bare string. Both flow.
            if isinstance(item, str):
                q = item.strip()
                rubric: Optional[dict] = None
            elif isinstance(item, dict):
                q = str(item.get("question") or item.get("q") or "").strip()
                rubric = _validate_rubric(item.get("rubric"))
            else:
                continue
            if q:
                pairs.append((q, rubric))
        return pairs or None

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
            f"For EACH question, also produce a per-question scoring rubric "
            f"with this exact structure:\n"
            f"  - `key_concepts`: a non-empty list of 2–5 short phrases naming "
            f"the specific concepts an excellent answer must address.\n"
            f"  - `anchors`: an object with the keys \"0\", \"1\", \"2\", \"3\", "
            f"\"4\", each mapping to a one-sentence description of an answer at "
            f"that level. Use this rubric:\n"
            f"      0 → No answer or completely off-topic\n"
            f"      1 → Vague — gestures at the topic without explaining it\n"
            f"      2 → Partial — describes some elements but misses key distinctions\n"
            f"      3 → Specific — explains the core concepts correctly\n"
            f"      4 → Exemplary — adds a concrete tradeoff, edge case, or example\n"
            f"The anchors must be specific to THIS question — not generic "
            f"placeholders. They are what the evaluator will use to anchor the "
            f"score.\n\n"
            f"Return ONLY a JSON array — no commentary, no markdown — where "
            f"each element has this exact shape:\n"
            f"[{{\"question\": \"<text>\", \"rubric\": {{\"key_concepts\": "
            f"[\"...\"], \"anchors\": {{\"0\": \"...\", \"1\": \"...\", "
            f"\"2\": \"...\", \"3\": \"...\", \"4\": \"...\"}}}}}}]"
        )
