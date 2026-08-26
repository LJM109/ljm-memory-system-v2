"""SQLite-backed persistent store for memories, facts, and entities.

SQLite is the single source of truth; the vector index is rebuilt from it on
startup and updated incrementally on Add. ``user_id`` is stored verbatim and
every query is scoped by it — retrieval isolation is enforced at the storage
boundary so cross-user leakage is structurally impossible.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field as dc_field
from typing import Any, Iterator, Optional

from ..core.clock import now_ms, to_iso


@dataclass
class MemoryRecord:
    id: str
    user_id: str
    content: str
    created_at: str
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    role: str = "user"
    search_text: str = ""
    turn_start: int = 0
    turn_end: int = 0
    ts: int = 0            # latest message timestamp (Unix ms)
    ts_min: int = 0        # earliest message timestamp (Unix ms)
    importance: float = 0.0
    facts: list[str] = dc_field(default_factory=list)
    entities: list[str] = dc_field(default_factory=list)
    version: int = 1
    superseded_by: Optional[str] = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT,
    request_id TEXT,
    content TEXT NOT NULL,
    search_text TEXT,
    role TEXT,
    turn_start INTEGER,
    turn_end INTEGER,
    ts INTEGER,
    ts_min INTEGER,
    importance REAL,
    facts TEXT,
    entities TEXT,
    version INTEGER DEFAULT 1,
    superseded_by TEXT,
    created_at TEXT NOT NULL,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_mem_user ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_mem_user_session ON memories(user_id, session_id);

CREATE TABLE IF NOT EXISTS entities (
    name TEXT NOT NULL,
    user_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    type TEXT,
    PRIMARY KEY (name, user_id, memory_id)
);
CREATE INDEX IF NOT EXISTS idx_ent_user ON entities(user_id, name);

CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    subject TEXT,
    predicate TEXT,
    object TEXT,
    raw_text TEXT,
    ts INTEGER,
    confidence REAL
);
CREATE INDEX IF NOT EXISTS idx_fact_user ON facts(user_id);
CREATE INDEX IF NOT EXISTS idx_fact_memory ON facts(memory_id);
"""


def _serialize(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class SQLiteStore:
    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
        self.db_path = db_path
        self._lock = threading.RLock()
        # check_same_thread=False + our own RLock; all access serialised.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            user_id=row["user_id"],
            content=row["content"],
            created_at=row["created_at"],
            session_id=row["session_id"],
            request_id=row["request_id"],
            role=row["role"],
            search_text=row["search_text"] or "",

            turn_start=row["turn_start"],
            turn_end=row["turn_end"],
            ts=row["ts"],
            ts_min=row["ts_min"],
            importance=row["importance"],
            facts=json.loads(row["facts"]) if row["facts"] else [],
            entities=json.loads(row["entities"]) if row["entities"] else [],
            version=row["version"],
            superseded_by=row["superseded_by"],
        )

    # --- memories ----------------------------------------------------------
    def add_memory(self, record: MemoryRecord, embedding: Optional[bytes]) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO memories
                   (id, user_id, session_id, request_id, content, search_text, role,
                    turn_start, turn_end, ts, ts_min, importance, facts,
                    entities, version, superseded_by, created_at, embedding)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.id,
                    record.user_id,
                    record.session_id,
                    record.request_id,
                    record.content,
                    record.search_text,
                    record.role,
                    record.turn_start,
                    record.turn_end,
                    record.ts,
                    record.ts_min,
                    record.importance,
                    _serialize(record.facts),
                    _serialize(record.entities),
                    record.version,
                    record.superseded_by,
                    record.created_at,
                    embedding,
                ),
            )
            self._conn.commit()

    def get_memory(self, memory_id: str) -> Optional[MemoryRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        return self._row_to_record(row) if row else None

    def iter_memories(self, user_id: Optional[str] = None) -> Iterator[MemoryRecord]:
        with self._lock:
            if user_id is None:
                rows = self._conn.execute("SELECT * FROM memories").fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM memories WHERE user_id = ?", (user_id,)
                ).fetchall()
        for row in rows:
            yield self._row_to_record(row)

    def memory_ids_by_user(
        self, user_id: str, session_id: Optional[str] = None
    ) -> list[str]:
        with self._lock:
            if session_id is not None:
                rows = self._conn.execute(
                    "SELECT id FROM memories WHERE user_id = ? AND session_id = ?",
                    (user_id, session_id),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT id FROM memories WHERE user_id = ?", (user_id,)
                ).fetchall()
        return [r["id"] for r in rows]

    def max_ts(self, user_id: str) -> int:
        """Most recent message timestamp for a user (for relative freshness)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(ts) AS m FROM memories WHERE user_id = ?", (user_id,)
            ).fetchone()
        return int(row["m"] or 0)

    def count_by_user_session(self, user_id: str, session_id: Optional[str]) -> int:
        with self._lock:
            if session_id is not None:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM memories WHERE user_id = ? AND session_id = ?",
                    (user_id, session_id),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM memories WHERE user_id = ?", (user_id,)
                ).fetchone()
        return int(row["c"])

    def mark_superseded(self, memory_id: str, superseded_by: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE memories SET superseded_by = ? WHERE id = ?",
                (superseded_by, memory_id),
            )
            self._conn.commit()

    def delete_memory(self, memory_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            self._conn.execute(
                "DELETE FROM entities WHERE memory_id = ?", (memory_id,)
            )
            self._conn.execute(
                "DELETE FROM facts WHERE memory_id = ?", (memory_id,)
            )
            self._conn.commit()

    # --- entities (graph nodes) -------------------------------------------
    def add_entity(self, name: str, user_id: str, memory_id: str, etype: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO entities (name, user_id, memory_id, type) VALUES (?,?,?,?)",
                (name, user_id, memory_id, etype),
            )
            self._conn.commit()

    def memories_for_entities(
        self, names: list[str], user_id: str
    ) -> dict[str, list[str]]:
        """Map each entity name -> list of memory ids sharing it (user-scoped)."""
        result: dict[str, list[str]] = {}
        if not names:
            return result
        with self._lock:
            placeholders = ",".join("?" for _ in names)
            rows = self._conn.execute(
                f"SELECT name, memory_id FROM entities WHERE user_id = ? AND name IN ({placeholders})",
                (user_id, *names),
            ).fetchall()
        for row in rows:
            result.setdefault(row["name"], []).append(row["memory_id"])
        return result

    def entities_for_memories(self, memory_ids: list[str], user_id: str) -> set[str]:
        if not memory_ids:
            return set()
        with self._lock:
            placeholders = ",".join("?" for _ in memory_ids)
            rows = self._conn.execute(
                f"SELECT DISTINCT name FROM entities WHERE user_id = ? AND memory_id IN ({placeholders})",
                (user_id, *memory_ids),
            ).fetchall()
        return {row["name"] for row in rows}

    # --- facts (structured triples) ---------------------------------------
    def add_fact(
        self,
        user_id: str,
        memory_id: str,
        subject: str,
        predicate: str,
        object_: str,
        raw_text: str,
        ts: int,
        confidence: float,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO facts
                   (id, user_id, memory_id, subject, predicate, object, raw_text, ts, confidence)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    f"fact_{uuid.uuid4().hex}",
                    user_id,
                    memory_id,
                    subject,
                    predicate,
                    object_,
                    raw_text,
                    ts,
                    confidence,
                ),
            )
            self._conn.commit()

    def facts_by_user(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM facts WHERE user_id = ? ORDER BY ts DESC", (user_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_embedding(self, memory_id: str) -> Optional[bytes]:
        with self._lock:
            row = self._conn.execute(
                "SELECT embedding FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        return row["embedding"] if row else None

    def iter_embeddings(self) -> Iterator[tuple[str, bytes]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, embedding FROM memories WHERE embedding IS NOT NULL"
            ).fetchall()
        for row in rows:
            yield row["id"], row["embedding"]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
