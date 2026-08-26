"""Ranking helpers (Mem0-style relevance/freshness/importance weighting)."""
from __future__ import annotations

import math

# Half-life for freshness decay (30 days in ms). Older memories decay toward
# zero so that temporal queries surface the latest valid state.
_FRESHNESS_TAU_MS = 30 * 24 * 3600 * 1000


def freshness_score(ts: int, now: int) -> float:
    if ts <= 0:
        return 0.5
    age_ms = max(0, now - ts)
    return math.exp(-age_ms / _FRESHNESS_TAU_MS)


def combine(
    semantic: float, freshness: float, importance: float, weights: tuple[float, float, float]
) -> float:
    """Weighted combination of the three ranking signals."""
    w_sem, w_fresh, w_imp = weights
    return w_sem * semantic + w_fresh * freshness + w_imp * importance
