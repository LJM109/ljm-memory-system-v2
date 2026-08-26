"""Incremental BM25 (Okapi) keyword index.

Keyword retrieval is the sparse half of the hybrid base (MemOS-style dense +
BM25). We implement BM25 directly with incremental document-frequency tracking
so adds are O(1) and scoring is O(docs) without rebuilding a corpus object.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

_TOKEN_RE = re.compile(r"[a-z0-9一-鿿]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_ids: list[str] = []
        self.doc_tokens: dict[str, list[str]] = {}
        self.doc_len: dict[str, int] = {}
        self.df: dict[str, int] = defaultdict(int)  # document frequency
        self.avgdl: float = 0.0
        self._total_len = 0

    @property
    def num_docs(self) -> int:
        return len(self.doc_ids)

    def _idf(self, term: str) -> float:
        n = self.num_docs
        df = self.df.get(term, 0)
        return math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    def add(self, doc_id: str, text: str) -> None:
        if doc_id in self.doc_tokens:
            self.remove(doc_id)
        tokens = tokenize(text)
        self.doc_ids.append(doc_id)
        self.doc_tokens[doc_id] = tokens
        self.doc_len[doc_id] = len(tokens)
        self._total_len += len(tokens)
        self.avgdl = self._total_len / max(1, self.num_docs)
        seen: set[str] = set()
        for term in tokens:
            if term not in seen:
                self.df[term] += 1
                seen.add(term)

    def remove(self, doc_id: str) -> None:
        if doc_id not in self.doc_tokens:
            return
        tokens = self.doc_tokens.pop(doc_id)
        self.doc_ids.remove(doc_id)
        self._total_len -= self.doc_len.pop(doc_id, 0)
        self.avgdl = self._total_len / max(1, self.num_docs)
        for term in set(tokens):
            self.df[term] -= 1
            if self.df[term] <= 0:
                self.df.pop(term, None)

    def score(self, query: str, doc_id: str) -> float:
        if doc_id not in self.doc_tokens:
            return 0.0
        tokens = self.doc_tokens[doc_id]
        if not tokens:
            return 0.0
        doc_len = self.doc_len[doc_id]
        counts: dict[str, int] = defaultdict(int)
        for term in tokens:
            counts[term] += 1
        score = 0.0
        for term in set(tokenize(query)):
            if term not in self.df:
                continue
            tf = counts.get(term, 0)
            if tf == 0:
                continue
            idf = self._idf(term)
            denom = tf + self.k1 * (1 - self.b + self.b * doc_len / max(1.0, self.avgdl))
            score += idf * tf * (self.k1 + 1.0) / denom
        return score

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        """Return top-k (doc_id, score) pairs sorted by descending score."""
        if self.num_docs == 0:
            return []
        scored = [(doc_id, self.score(query, doc_id)) for doc_id in self.doc_ids]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:k]
