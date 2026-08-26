"""In-memory cosine-similarity vector index.

Holds a dense float32 matrix keyed by memory id. Search is a single matrix
product over the (user-scoped) allowed subset, which is fast enough at the
benchmark scale (thousands of 384-dim vectors) without an external ANN index.
"""
from __future__ import annotations

import threading
from typing import Optional

import numpy as np


class VectorStore:
    def __init__(self, dim: int) -> None:
        self.dim = dim
        self._ids: list[str] = []
        self._matrix: Optional[np.ndarray] = None  # (n, dim), L2-normalised rows
        self._index: dict[str, int] = {}
        self._lock = threading.RLock()

    @property
    def size(self) -> int:
        return len(self._ids)

    def add(self, doc_id: str, vec: np.ndarray) -> None:
        vec = np.asarray(vec, dtype=np.float32).reshape(1, -1)
        if vec.shape[1] != self.dim:
            raise ValueError(f"vector dim {vec.shape[1]} != index dim {self.dim}")
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        with self._lock:
            if doc_id in self._index:
                self._matrix[self._index[doc_id]] = vec[0]
                return
            self._ids.append(doc_id)
            self._index[doc_id] = len(self._ids) - 1
            self._matrix = (
                vec.copy()
                if self._matrix is None
                else np.vstack([self._matrix, vec])
            )

    def remove(self, doc_id: str) -> None:
        with self._lock:
            idx = self._index.get(doc_id)
            if idx is None:
                return
            # Swap-remove keeps the matrix compact; ids order not preserved.
            last = len(self._ids) - 1
            last_id = self._ids[last]
            self._matrix[idx] = self._matrix[last]
            self._ids[idx] = last_id
            self._index[last_id] = idx
            self._ids.pop()
            self._index.pop(doc_id, None)
            self._matrix = self._matrix[:last]

    def search(
        self,
        query_vec: np.ndarray,
        k: int,
        allowed_ids: Optional[set[str]] = None,
    ) -> list[tuple[str, float]]:
        """Return top-k (doc_id, cosine score) over the allowed subset."""
        with self._lock:
            if self._matrix is None or self.size == 0:
                return []
            q = np.asarray(query_vec, dtype=np.float32).reshape(1, -1)
            if allowed_ids is None:
                scores = (self._matrix @ q.T).reshape(-1)
                order = np.argsort(-scores)[:k]
                return [(self._ids[i], float(scores[i])) for i in order]
            rows = [self._index[i] for i in allowed_ids if i in self._index]
            if not rows:
                return []
            sub = self._matrix[rows]
            scores = (sub @ q.T).reshape(-1)
            order = np.argsort(-scores)[: min(k, len(rows))]
            return [
                (self._ids[rows[i]], float(scores[i])) for i in order
            ]
