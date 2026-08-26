"""Importance scoring (Mem0-style heuristic).

Scores how valuable a memory chunk is likely to be, driving both retrieval
ranking and retention. Higher scores for user-authored, fact-bearing,
preference- and rule-laden content; lower for short ack/pleasantry turns.
"""
from __future__ import annotations

import re

from ..config import settings

_PREF_WORDS = re.compile(
    r"\b(?:like|love|prefer|enjoy|favorite|favourite|hate|dislike)\b", re.IGNORECASE
)
_RULE_WORDS = re.compile(
    r"\b(?:always|never|must|should|have to|need to|remember|rule|policy)\b",
    re.IGNORECASE,
)
_IDENTITY_WORDS = re.compile(
    r"\b(?:I am|I'm|my name|I live|I work|I was born|my)\b", re.IGNORECASE
)
_NUMBER = re.compile(r"\b\d[\d,.]*\b")


def score_chunk(text: str, role: str, num_facts: int, num_entities: int) -> float:
    """Return an importance score in [0, 1]."""
    length = len(text.strip())
    if length == 0:
        return 0.0

    # Base from length: 0..1 capped at ~600 chars.
    base = min(1.0, length / 600.0) * 0.5

    # Content signals.
    signal = 0.0
    if _PREF_WORDS.search(text):
        signal += settings.importance_preference_boost
    if _RULE_WORDS.search(text):
        signal += settings.importance_rule_boost
    if _IDENTITY_WORDS.search(text):
        signal += settings.importance_fact_boost * 0.5
    if _NUMBER.search(text):
        signal += 0.1
    if num_facts > 0:
        signal += min(0.2, 0.05 * num_facts)
    if num_entities > 0:
        signal += min(0.15, 0.05 * num_entities)

    # Speaker weighting: user-authored memories carry more signal.
    role_factor = 1.0 if role == "user" else 0.75

    return min(1.0, (base + signal) * role_factor)
