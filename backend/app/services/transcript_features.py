"""Lightweight transcript-derived features for the integrity panel.

These are *soft signals*. None of them, individually or together, prove a
candidate cheated. They surface to the recruiter as a pattern-of-evidence
panel — sudden vocabulary jumps, rhetorical structure that looks more
like a written outline than spoken English, etc. The most useful
within-candidate signal is *change*: the same candidate becoming
suspiciously fluent on answer 5.

We deliberately don't reach for AI-text-detection here. Published evidence
puts those at ~61% false-positive rate on non-native English writers, which
on Whisper transcripts of spoken English is almost certainly worse, and
the EU AI Act / NYC LL 144 / Mobley v. Workday backdrop makes accuracy
claims a liability vector.

All functions tolerate empty / None input by returning sensible zero
values. Callers should feed `whisper_transcript or transcript`.
"""

from __future__ import annotations

import re
from statistics import pvariance
from typing import Any, Dict


# Discourse markers and rhetorical scaffolding. Heavy use of these is a
# stronger written-text signal than any single suspicious word would be.
_STRUCTURAL_MARKERS = (
    "firstly",
    "secondly",
    "thirdly",
    "fourthly",
    "in conclusion",
    "to summarize",
    "to summarise",
    "in summary",
    "moreover",
    "furthermore",
    "additionally",
    "in addition",
    "consequently",
    "therefore",
    "nevertheless",
    "however",
    "on the other hand",
    "for instance",
    "for example",
)

_NUMBERED_LIST_RE = re.compile(r"\b(\d+)[\.\)]\s+\w", re.MULTILINE)
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
_WORD_RE = re.compile(r"\b[\w'-]+\b")


def word_count(transcript: str | None) -> int:
    if not transcript:
        return 0
    return len(_WORD_RE.findall(transcript))


def sentence_length_variance(transcript: str | None) -> float:
    """Population variance of words-per-sentence. Polished written text
    tends to have tighter, more uniform sentence lengths than spontaneous
    spoken answers. Returns 0.0 when the input has fewer than two
    non-empty sentences."""
    if not transcript:
        return 0.0
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(transcript) if s.strip()]
    if len(sentences) < 2:
        return 0.0
    lengths = [len(_WORD_RE.findall(s)) for s in sentences]
    return float(pvariance(lengths))


def structural_marker_count(transcript: str | None) -> int:
    """Count occurrences of discourse markers + numbered-list patterns
    that are unusual in spontaneous speech."""
    if not transcript:
        return 0
    lowered = transcript.lower()
    marker_hits = sum(lowered.count(marker) for marker in _STRUCTURAL_MARKERS)
    numbered_hits = len(_NUMBERED_LIST_RE.findall(transcript))
    return marker_hits + numbered_hits


def extract_features(transcript: str | None) -> Dict[str, Any]:
    """Bundle the features into the JSON shape we persist on Answer."""
    return {
        "word_count": word_count(transcript),
        "sentence_length_variance": round(sentence_length_variance(transcript), 3),
        "structural_marker_count": structural_marker_count(transcript),
    }
