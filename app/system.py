"""MemorySystem facade wiring ingest, storage, retrieval, and governance.

This is the single orchestration point behind the FastAPI endpoints. All
state-mutating operations are serialised under one lock; reads (Search) reuse
the same lock so the synchronous Add/Search contract holds under concurrency.
"""
from __future__ import annotations

import hashlib
import threading
from typing import Optional

import numpy as np

from .config import settings
from .core.bm25 import BM25Index
from .core.clock import now_ms, to_iso
from .core.embedding import get_embedding_model
from .governance.conflict import resolve_conflicts
from .governance.retention import prune_session
from .ingest.chunker import chunk_messages
from .ingest.dedup import find_duplicate
from .ingest.extractor import extract_with_llm
from .ingest.scoring import score_chunk
from .retrieval.hybrid import Retriever
from .schemas import AddMessage
from .storage.sqlite_store import MemoryRecord, SQLiteStore
from .storage.vector_store import VectorStore


class MemorySystem:
    def __init__(self) -> None:
        self.embedder = get_embedding_model()
        self.store = SQLiteStore(settings.db_path)
        self.vector = VectorStore(self.embedder.dim)
        self.bm25 = BM25Index()
        self.retriever = Retriever(self.store, self.vector, self.bm25, self.embedder)
        self._lock = threading.RLock()
        self._rebuild()

    # -- lifecycle ----------------------------------------------------------
    def _rebuild(self) -> None:
        """Rehydrate the vector + BM25 indexes from persisted SQLite state."""
        for mid, blob in self.store.iter_embeddings():
            record = self.store.get_memory(mid)
            if record is None or record.superseded_by:
                continue
            vec = np.frombuffer(blob, dtype=np.float32)
            self.vector.add(mid, vec)
            self.bm25.add(mid, record.search_text or record.content)

    @staticmethod
    def _make_id(
        user_id: str, session_id: Optional[str], request_id: str, start: int, end: int
    ) -> str:
        raw = f"{user_id}|{session_id}|{request_id}|{start}|{end}"
        return "mem_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]

    # -- write --------------------------------------------------------------
    def add(
        self,
        user_id: str,
        session_id: Optional[str],
        request_id: Optional[str],
        messages: list[AddMessage],
    ) -> str:
        rid = request_id or hashlib.sha1(
            f"{user_id}|{session_id}|{now_ms()}".encode("utf-8")
        ).hexdigest()[:16]

        chunks = chunk_messages(messages)
        with self._lock:
            allowed = set(self.store.memory_ids_by_user(user_id))
            for chunk in chunks:
                entities, facts = extract_with_llm(chunk.raw_texts)
                importance = score_chunk(
                    chunk.text, chunk.role, len(facts), len(entities)
                )
                # Index the clean raw text (no timestamp/role prefix) so the
                # semantic signal is not polluted; `content` keeps the metadata
                # for the answer model.
                search_text = "\n".join(chunk.raw_texts).strip() or chunk.text
                vec = self.embedder.embed_one(search_text)

                # Hindsight-style noise reduction: skip near-duplicate restatements.
                if find_duplicate(vec, self.vector, allowed, settings.dedup_similarity):
                    continue

                mem_id = self._make_id(
                    user_id, session_id, rid, chunk.turn_start, chunk.turn_end
                )
                entity_names = [name for name, _etype in entities]
                record = MemoryRecord(
                    id=mem_id,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=rid,
                    content=chunk.text,
                    search_text=search_text,
                    role=chunk.role,
                    turn_start=chunk.turn_start,
                    turn_end=chunk.turn_end,
                    ts=chunk.ts or now_ms(),
                    ts_min=chunk.ts_min or chunk.ts or now_ms(),
                    importance=importance,
                    facts=facts,
                    entities=entity_names,
                    created_at=to_iso(chunk.ts or now_ms()),
                )

                self.store.add_memory(record, vec.tobytes())
                self.vector.add(mem_id, vec)
                self.bm25.add(mem_id, search_text)
                for name, etype in entities:
                    self.store.add_entity(name, user_id, mem_id, etype)
                for fact in facts:
                    self.store.add_fact(
                        user_id,
                        mem_id,
                        subject="",
                        predicate="",
                        object_="",
                        raw_text=fact,
                        ts=record.ts,
                        confidence=min(1.0, importance),
                    )
                allowed.add(mem_id)

                # Cognee-style conflict detection / versioning.
                for old_id in resolve_conflicts(self.store, user_id, mem_id, facts):
                    old = self.store.get_memory(old_id)
                    if old is not None and not old.superseded_by:
                        self.store.mark_superseded(old_id, mem_id)
                        self.vector.remove(old_id)
                        self.bm25.remove(old_id)

            if session_id:
                prune_session(self.store, user_id, session_id)

        return rid

    # -- read ---------------------------------------------------------------
    def search(
        self,
        query: str,
        user_id: str,
        top_k: int,
        options: Optional[list[str]] = None,
    ) -> list[dict]:
        with self._lock:
            ranked = self.retriever.search(query, user_id, top_k, options)
        results: list[dict] = []
        for record, score in ranked:
            results.append(
                {
                    "id": record.id,
                    "content": record.content,
                    "score": round(max(0.0, min(1.0, score)), 6),
                    "created_at": record.created_at,
                }
            )
        return results

    def health(self) -> dict:
        return {"status": "ok"}
