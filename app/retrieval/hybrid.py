"""Hybrid retrieval (MemOS dense + BM25 base, Cognee graph path) with rerank.

Three recall paths — dense cosine, BM25 keyword, and entity-graph — are fused
with reciprocal-rank fusion, then the fused candidate set is re-ranked by a
weighted combination of semantic similarity, temporal freshness, and importance
(Mem0-style). The result is returned ordered most-to-least relevant, respecting
the AML Search contract.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from ..config import settings
from ..core.bm25 import BM25Index
from ..core.clock import now_ms
from ..core.embedding import EmbeddingModel
from ..storage.sqlite_store import MemoryRecord, SQLiteStore
from ..storage.vector_store import VectorStore
from .graph_recall import recall as graph_recall
from .rank import combine as combine_scores
from .rank import freshness_score

_RRF_K = 60.0


class Retriever:
    def __init__(
        self,
        store: SQLiteStore,
        vector_store: VectorStore,
        bm25: BM25Index,
        embedder: EmbeddingModel,
    ) -> None:
        self.store = store
        self.vector_store = vector_store
        self.bm25 = bm25
        self.embedder = embedder

    def search(
        self,
        query: str,
        user_id: str,
        top_k: int,
        options: Optional[list[str]] = None,
    ) -> list[tuple[MemoryRecord, float]]:
        # Enrich the query with choice options so retrieval can match option
        # text (harmless for open-ended queries where options is None).
        search_query = query
        if options:
            search_query = query + "\n" + "\n".join(options)

        allowed_ids = set(self.store.memory_ids_by_user(user_id))
        if not allowed_ids:
            return []

        query_vec = self.embedder.embed_query(search_query)

        # --- multi-path recall -------------------------------------------
        dense = self.vector_store.search(query_vec, settings.dense_recall, allowed_ids)
        bm25 = [
            (mid, s)
            for mid, s in self.bm25.search(search_query, settings.bm25_recall)
            if mid in allowed_ids
        ]
        graph = [
            (mid, s)
            for mid, s in graph_recall(search_query, user_id, self.store, settings.graph_recall)
            if mid in allowed_ids
        ]

        # --- reciprocal-rank fusion --------------------------------------
        rankings = {"dense": dense, "bm25": bm25, "graph": graph}
        weights = {
            "dense": settings.fuse_dense,
            "bm25": settings.fuse_bm25,
            "graph": settings.fuse_graph,
        }
        fused: dict[str, float] = {}
        for path, ranked in rankings.items():
            for rank, (mid, _) in enumerate(ranked):
                fused[mid] = fused.get(mid, 0.0) + weights[path] / (_RRF_K + rank + 1)

        # --- load records + compute rerank signals ------------------------
        # Relative freshness reference: the user's newest memory. Using wall
        # clock would decay all benchmark timestamps toward zero and erase the
        # temporal signal for "latest valid state" questions.
        now = self.store.max_ts(user_id) or now_ms()
        records: dict[str, MemoryRecord] = {}
        dense_sim: dict[str, float] = {mid: s for mid, s in dense}
        bm25_scores: dict[str, float] = {mid: s for mid, s in bm25}
        graph_scores: dict[str, float] = {mid: s for mid, s in graph}
        for mid in fused:
            record = self.store.get_memory(mid)
            if record is None or record.superseded_by:
                continue
            records[mid] = record

        # Compute semantic similarity for every candidate (dense already has it;
        # the rest are computed on demand).
        semantic_by_mid: dict[str, float] = dict(dense_sim)
        for mid, record in records.items():
            if mid not in semantic_by_mid:
                vec = self.embedder.embed_one(record.search_text or record.content)
                semantic_by_mid[mid] = float(np.dot(vec, query_vec))

        # Epistemic-safety gate (query-level): if NO candidate has any real
        # signal (semantic >= min_semantic, or a BM25 keyword hit, or a graph
        # path), the query is irrelevant -> return empty. Otherwise the query is
        # relevant, and we keep the FULL candidate set so multi-hop evidence
        # chains (whose intermediate hops may lack keyword overlap) are not
        # dropped by a per-candidate semantic floor. min_semantic is calibrated
        # (0.52) above bge-small's unrelated-text cosine baseline (~0.35-0.45).
        has_signal = any(
            semantic_by_mid.get(mid, 0.0) >= settings.min_semantic
            or bm25_scores.get(mid, 0.0) > 1e-9
            or graph_scores.get(mid, 0.0) > 0.0
            for mid in records
        )
        if not has_signal:
            return []

        # Re-rank all candidates by (semantic, freshness, importance).
        ranked_results: list[tuple[MemoryRecord, float]] = []
        for mid, record in records.items():
            semantic = semantic_by_mid[mid]
            fresh = freshness_score(record.ts, now)
            importance = max(0.0, min(1.0, record.importance))
            final = combine_scores(
                semantic,
                fresh,
                importance,
                (
                    settings.rerank_semantic,
                    settings.rerank_freshness,
                    settings.rerank_importance,
                ),
            )
            ranked_results.append((record, final))

        ranked_results.sort(key=lambda pair: pair[1], reverse=True)
        return ranked_results[:top_k]
