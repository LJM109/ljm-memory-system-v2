"""Temporal chunking (MemOS event blocks + MemPalace chunking).

Turns an ordered message list into memory chunks that preserve (a) temporal
order, (b) speaker/role attribution, and (c) a bounded chunk size so long
contexts are stored as several coherent, independently retrievable memories
rather than one giant blob.

Design: consecutive messages from the same speaker are folded into a single
chunk (an "event block") until the character/turn budget is reached. This keeps
the user's facts/preferences in the user's own blocks, which matters for
personalization and ScriptMem-style speaker attribution.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Optional

from ..config import settings
from ..core.clock import to_iso
from ..schemas import AddMessage


@dataclass
class Chunk:
    text: str                       # formatted evidence text (returned to AML)
    role: str                       # dominant role of the block
    ts: int                         # latest message timestamp (Unix ms)
    ts_min: int                     # earliest message timestamp (Unix ms)
    turn_start: int                 # first message index (0-based)
    turn_end: int                   # last message index (inclusive)
    raw_texts: list[str] = dc_field(default_factory=list)


def _format(content: str, role: str, ts_ms: Optional[int]) -> str:
    role_label = role.strip() or "user"
    if ts_ms:
        return f"[{to_iso(ts_ms)}] {role_label}: {content}"
    return f"{role_label}: {content}"


def _split_long(text: str, max_chars: int) -> list[str]:
    """Split over-long text on sentence/whitespace boundaries."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    current = ""
    for piece in text.split("\n"):
        if len(current) + len(piece) + 1 <= max_chars:
            current = f"{current}\n{piece}" if current else piece
        else:
            if current:
                parts.append(current)
            # Further split very long single lines.
            while len(piece) > max_chars:
                parts.append(piece[:max_chars])
                piece = piece[max_chars:]
            current = piece
    if current:
        parts.append(current)
    return parts


def chunk_messages(messages: list[AddMessage]) -> list[Chunk]:
    """Produce ordered chunks from ordered messages."""
    chunks: list[Chunk] = []
    if not messages:
        return chunks

    cur_role: Optional[str] = None
    cur_texts: list[str] = []
    cur_raw: list[str] = []
    cur_ts: Optional[int] = None
    cur_ts_min: Optional[int] = None
    cur_start = 0

    def flush(end_idx: int) -> None:
        nonlocal cur_role, cur_texts, cur_raw, cur_ts, cur_ts_min
        if not cur_texts:
            return
        ts = cur_ts or 0
        ts_min = cur_ts_min or ts
        formatted = "\n".join(cur_texts)
        for part in _split_long(formatted, settings.chunk_max_chars):
            chunks.append(
                Chunk(
                    text=part,
                    role=cur_role or "user",
                    ts=ts,
                    ts_min=ts_min,
                    turn_start=cur_start,
                    turn_end=end_idx,
                    raw_texts=list(cur_raw),
                )
            )
        cur_role = None
        cur_texts = []
        cur_raw = []
        cur_ts = None
        cur_ts_min = None

    for idx, msg in enumerate(messages):
        role = (msg.role or "user").strip()
        content = msg.content or ""
        ts = msg.timestamp
        if content == "" and role == "":
            continue
        # Start a new block when the speaker changes or the turn budget is hit.
        if role != cur_role or len(cur_texts) >= settings.chunk_max_turns:
            flush(idx - 1)
            cur_role = role
            cur_start = idx
        cur_texts.append(_format(content, role, ts))
        cur_raw.append(content)
        if ts:
            cur_ts = ts if cur_ts is None else max(cur_ts, ts)
            cur_ts_min = ts if cur_ts_min is None else min(cur_ts_min, ts)

    flush(len(messages) - 1)
    return chunks
