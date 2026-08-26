"""Deduplication / noise reduction (Vectorize Hindsight-style).

Near-duplicate memories (repeated restatements of the same fact) add noise
without improving recall. On ingest we detect an incoming chunk that is nearly
identical to an existing user memory and fold it in (skip the redundant store)
or, when the incoming chunk is a superset, merge it and keep the richer version.
"""
from __future__ import annotations

from typing import Optional

from ..config import settings


def find_duplicate(
    new_embedding,
    vector_store,
    allowed_ids: set[str],
    threshold: Optional[float] = None,
) -> Optional[tuple[str, float]]:
    """Return (memory_id, similarity) of the top existing match if above the
    threshold, else None."""
    threshold = threshold if threshold is not None else settings.dedup_similarity
    top = vector_store.search(new_embedding, 1, allowed_ids=allowed_ids)
    if not top:
        return None
    doc_id, similarity = top[0]
    if similarity >= threshold:
        return doc_id, similarity
    return None
