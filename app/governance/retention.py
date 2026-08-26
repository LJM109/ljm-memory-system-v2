"""Retention / eviction (MemOS expiry + Mem0 importance-based cleanup).

Keeps per-session memory bounded when configured: beyond the cap, the
lowest-importance memories are evicted so high-value facts survive. Disabled by
default (``RETENTION_MAX_PER_SESSION=0``) so no evidence is silently dropped in
a benchmark run unless the operator opts in.
"""
from __future__ import annotations

from ..config import settings
from ..storage.sqlite_store import SQLiteStore


def prune_session(store: SQLiteStore, user_id: str, session_id: str) -> int:
    """Evict low-importance memories beyond the per-session cap. Returns the
    number of memories removed (0 when pruning is disabled)."""
    cap = settings.retention_max_per_session
    if cap <= 0 or session_id is None:
        return 0

    records = [
        r for r in store.iter_memories(user_id) if r.session_id == session_id
    ]
    if len(records) <= cap:
        return 0

    records.sort(key=lambda r: (r.importance, r.ts))  # lowest importance first
    to_remove = records[: len(records) - cap]
    for record in to_remove:
        store.delete_memory(record.id)
    return len(to_remove)
