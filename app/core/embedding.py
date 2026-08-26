"""Embedding wrapper (fastembed) with a deterministic hashing fallback.

Primary path is a local ONNX sentence-transformer (downloaded at Docker build
time), which keeps Add/Search self-contained and deterministic. If the model is
unavailable, a feature-hashing embedding keeps the service functional so it
never hard-crashes (and unit tests run offline). The fallback is deliberately
weak on semantics; BM25 remains the keyword backstop in both cases.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Optional

import numpy as np

from ..config import settings

_TOKEN_RE = re.compile(r"[a-z0-9一-鿿]+")


class EmbeddingModel:
    """Lazily-initialised embedding model with a hashing fallback."""

    def __init__(self, dim: int = 0) -> None:
        self._dim = dim or settings.embedding_dim
        self._model = None
        self._tried = False
        self._query_instruction = self._detect_instruction()

    @staticmethod
    def _detect_instruction() -> str:
        model = settings.embedding_model.lower()
        if "bge" in model:
            return "Represent this sentence for searching relevant passages: "
        if "e5" in model:
            return "query: "
        return ""

    @property
    def dim(self) -> int:
        return self._dim

    def _load(self) -> None:
        if self._tried:
            return
        self._tried = True
        try:
            from fastembed import TextEmbedding

            # The model weights are pre-downloaded into the image at build time,
            # so load them from the local cache only. Passing local_files_only
            # avoids a runtime network round-trip (which fails behind the
            # firewall and silently degrades to the hashing fallback).
            model = TextEmbedding(
                model_name=settings.embedding_model, local_files_only=True
            )
            # Warm up and learn the true dimension.
            probe = next(model.embed(["warmup"]))
            self._model = model
            self._dim = int(probe.shape[0])
        except Exception:
            self._model = None

    @property
    def using_fallback(self) -> bool:
        self._load()
        return self._model is None

    def _hash_vec(self, text: str) -> np.ndarray:
        """Deterministic feature-hashing embedding (fallback path)."""
        vec = np.zeros(self._dim, dtype=np.float32)
        tokens = _TOKEN_RE.findall(text.lower())
        if not tokens:
            tokens = ["<empty>"]
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            # Hash each token into a couple of buckets to reduce collisions.
            for offset in (0, 4, 8):
                idx = int.from_bytes(digest[offset : offset + 4], "little") % self._dim
                vec[idx] += 1.0
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec.astype(np.float32)

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts into a (n, dim) float32 array."""
        self._load()
        if self._model is not None:
            vectors = list(self._model.embed([t or " " for t in texts]))
            matrix = np.asarray(vectors, dtype=np.float32)
            if matrix.shape[0] != len(texts):
                # Edge case: model returned an unexpected shape; fall back.
                matrix = np.vstack([self._hash_vec(t) for t in texts])
        else:
            matrix = np.vstack([self._hash_vec(t) for t in texts])
        # L2-normalise for cosine similarity.
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (matrix / norms).astype(np.float32)

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a search query with the model's query-instruction prefix.

        bge/E5 models are trained with a query-side instruction; omitting it
        inflates the cosine baseline for unrelated text and weakens the
        epistemic-safety relevance gate.
        """
        instruction = settings.query_instruction or self._query_instruction
        if instruction:
            return self.embed([instruction + text])[0]
        return self.embed_one(text)


_model_singleton: Optional[EmbeddingModel] = None


def get_embedding_model() -> EmbeddingModel:
    global _model_singleton
    if _model_singleton is None:
        _model_singleton = EmbeddingModel()
    return _model_singleton
