"""Skill catalog and normalization helpers used by the question bank.

`normalize_skills_key` is the canonical form used as the bank lookup key:
lowercased, trimmed, deduplicated, sorted, comma-joined. An empty list maps
to the empty string so rows generated for "no skills picked" still cluster.

`GENERAL_SKILLS` are soft skills offered alongside every topic in the UI —
they apply to any role, not a specific technical area.
"""

from __future__ import annotations

from typing import Iterable, List


GENERAL_SKILLS: List[str] = [
    "Communication",
    "Problem solving",
    "Team management",
    "Leadership",
    "Ownership",
    "Collaboration",
]


def normalize_skills_key(skills: Iterable[str] | None) -> str:
    if not skills:
        return ""
    cleaned = {s.strip().lower() for s in skills if s and s.strip()}
    return ",".join(sorted(cleaned))


def normalize_skills_list(skills: Iterable[str] | None) -> List[str]:
    """Return a deduped, trimmed list preserving the user's casing on the
    first occurrence of each skill. Used when persisting `skills_json`."""
    if not skills:
        return []
    seen: dict[str, str] = {}
    for s in skills:
        if not s or not s.strip():
            continue
        key = s.strip().lower()
        if key not in seen:
            seen[key] = s.strip()
    return list(seen.values())
