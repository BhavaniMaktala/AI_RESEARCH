"""BM25 lexical index - used to pre-filter large candidate pools before
semantic reranking (hybrid retrieval)."""
from __future__ import annotations

import math
import re
from collections import Counter

from services.nlp import STOPWORDS

_TOKEN = re.compile(r"[a-z][a-z0-9\-]{1,}")


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in STOPWORDS]


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_ids: list[str] = []
        self._tf: list[Counter] = []
        self._len: list[int] = []
        self._df: Counter = Counter()
        self._avgdl: float = 0.0

    def build(self, docs: list[tuple[str, str]]) -> None:
        self.doc_ids, self._tf, self._len = [], [], []
        self._df = Counter()
        for pid, text in docs:
            toks = _tokens(text)
            tf = Counter(toks)
            self.doc_ids.append(pid)
            self._tf.append(tf)
            self._len.append(len(toks))
            for term in tf:
                self._df[term] += 1
        n = max(1, len(self.doc_ids))
        self._avgdl = sum(self._len) / n if self._len else 0.0

    def search(self, query: str, k: int = 50) -> list[tuple[str, float]]:
        terms = _tokens(query)
        if not terms or not self.doc_ids:
            return []
        n = len(self.doc_ids)
        scores: list[float] = [0.0] * n
        for term in set(terms):
            df = self._df.get(term, 0)
            if df == 0:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for i, tf in enumerate(self._tf):
                f = tf.get(term, 0)
                if not f:
                    continue
                dl = self._len[i] or 1
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self._avgdl or 1))
                scores[i] += idf * (f * (self.k1 + 1)) / denom
        ranked = sorted(((s, i) for i, s in enumerate(scores) if s > 0), reverse=True)[:k]
        return [(self.doc_ids[i], float(s)) for s, i in ranked]

    def __len__(self) -> int:
        return len(self.doc_ids)
