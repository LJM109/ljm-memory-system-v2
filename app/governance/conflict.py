"""Fact conflict detection + versioning (Cognee-style).

Detects when a newly-ingested fact updates/contradicts an earlier fact about
the same subject (same normalized key, different value) and marks the older,
single-fact memory as superseded so temporal queries surface the latest valid
state. Conservative by design: only a memory whose factual payload is fully
covered by the update is superseded; richer memories are left intact.
"""
from __future__ import annotations

import re
from typing import Optional

from ..storage.sqlite_store import SQLiteStore

_LOCATION_RE = re.compile(
    r"\b(?:live in|live at|lives in|lives at|moved? to|relocated? to|from)\s+([A-Za-z][A-Za-z .]{1,60})",
    re.IGNORECASE,
)
_JOB_RE = re.compile(
    r"\b(?:work at|work for|works at|works for|employed at|job at)\s+([A-Za-z][A-Za-z .]{1,60})",
    re.IGNORECASE,
)
_NAME_RE = re.compile(r"\b(?:name is|my name is|call me|I'm called)\s+([A-Za-z][A-Za-z .]{1,60})", re.IGNORECASE)


def _fact_key(fact: str) -> Optional[tuple[str, str]]:
    """Normalize a fact string to (key, value) if it is a *single-value*
    attribute that can be superseded by an update, else None.

    Only mutually-exclusive attributes (location, job, name) are conflict
    candidates. Preferences / likes / rules are additive — a user can love both
    hiking and painting — so they are deliberately excluded from conflict
    detection and never trigger supersession.
    """
    lowered = fact.lower().strip()
    # Name facts from the extractor carry an explicit "name:" prefix; key on it
    # directly so "My name is X" / "Call me X" / "I'm called X" / "I'm X" all
    # map to the same mutually-exclusive "name" attribute.
    if lowered.startswith("name:"):
        value = lowered[len("name:"):].strip().strip(".,; ")
        if 2 <= len(value) <= 60:
            return "name", _normalize(value)
    for kind, regex in (
        ("location", _LOCATION_RE),
        ("job", _JOB_RE),
        ("name", _NAME_RE),
    ):
        match = regex.search(lowered)
        if match:
            value = match.group(1).strip().strip(".,; ")
            if 2 <= len(value) <= 60:
                return kind, _normalize(value)
    return None


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def resolve_conflicts(
    store: SQLiteStore,
    user_id: str,
    new_memory_id: str,
    new_facts: list[str],
) -> list[str]:
    """Return ids of older memories to supersede given the new facts.

    Conservative: a memory is superseded only when *all* of its extracted facts
    conflict with the new state (i.e. it is a single-fact statement that has
    since been updated). Richer memories keep their non-conflicting facts.
    """
    new_keys: dict[str, str] = {}
    for fact in new_facts:
        parsed = _fact_key(fact)
        if parsed:
            key, value = parsed
            new_keys.setdefault(key, value)

    if not new_keys:
        return []

    per_memory_total: dict[str, int] = {}
    per_memory_conflict: dict[str, int] = {}
    for fact_row in store.facts_by_user(user_id):
        mid = fact_row["memory_id"]
        if mid == new_memory_id:
            continue
        per_memory_total[mid] = per_memory_total.get(mid, 0) + 1
        parsed = _fact_key(fact_row["raw_text"] or "")
        if not parsed:
            continue
        key, old_value = parsed
        if key in new_keys and old_value != new_keys[key]:
            per_memory_conflict[mid] = per_memory_conflict.get(mid, 0) + 1

    return [
        mid
        for mid, total in per_memory_total.items()
        if per_memory_conflict.get(mid, 0) > 0
        and per_memory_conflict.get(mid, 0) == total
    ]
