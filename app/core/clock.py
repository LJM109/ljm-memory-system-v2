"""Timestamp helpers.

The AML contract stores message timestamps in Unix milliseconds and returns a
``created_at`` field on search results. We keep both a Unix-ms integer (for
temporal ordering) and an ISO-8601 string (for the response) so downstream
temporal/event-ordering reasoning and the API contract are both satisfied.
"""
from __future__ import annotations

from datetime import datetime, timezone


def now_ms() -> int:
    """Current time in Unix milliseconds."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def to_iso(ts_ms: int | None) -> str:
    """Convert a Unix-ms timestamp (or None -> now) to an ISO-8601 string."""
    if ts_ms is None:
        ts_ms = now_ms()
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def iso_to_ms(value: str) -> int:
    """Best-effort parse of an ISO-8601 string back to Unix milliseconds."""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except (ValueError, AttributeError):
        return 0
