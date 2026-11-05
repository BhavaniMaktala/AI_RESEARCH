"""Vector index backends: FAISS when available, NumPy otherwise."""
from __future__ import annotations

import logging
import threading
from typing import Sequence

import numpy as np

log = logging.getLogger(__name__)


class BaseVectorStore:
    backend = "base"

    def __init__(self, dim: int):
        self.dim = dim
        self.ids: list[str] = []
        self._pos: dict[str, int] = {}

    def build(self, ids: Sequence[str], vectors: np.ndarray) -> None:
        raise NotImplementedError

    def search(self, vector: np.ndarray, k: int = 10) -> list[tuple[str, float]]:
        raise NotImplementedError

    def __len__(self) -> int:
        return len(self.ids)

    def info(self) -> dict:
        return {"backend": self.backend, "vectors": len(self.ids), "dim": self.dim}


class NumpyVectorStore(BaseVectorStore):
    """Exact cosine search with a single matrix multiply. Fine up to ~1e5 docs."""

    backend = "numpy"

    def __init__(self, dim: int):
        super().__init__(dim)
        self._matrix = np.zeros((0, dim), dtype="float32")

    def build(self, ids: Sequence[str], vectors: np.ndarray) -> None:
        self.ids = list(ids)
        self._pos = {pid: i for i, pid in enumerate(self.ids)}
        matrix = np.asarray(vectors, dtype="float32")
        if matrix.size == 0:
            self._matrix = np.zeros((0, self.dim), dtype="float32")
        else:
            self._matrix = matrix

    def search(self, vector: np.ndarray, k: int = 10) -> list[tuple[str, float]]:
        if not self.ids or self._matrix.size == 0:
            return []
        q = np.asarray(vector, dtype="float32").reshape(-1)
        scores = self._matrix @ q
        k = min(k, len(self.ids))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(self.ids[i], float(scores[i])) for i in top]


class FaissVectorStore(BaseVectorStore):
    """FAISS inner-product index (cosine, since vectors are normalised)."""

    backend = "faiss"

    def __init__(self, dim: int):
        import faiss  # noqa: F401 - validated here so the factory can fall back

        super().__init__(dim)
        self._index = faiss.IndexFlatIP(dim)
        self._faiss = faiss
        self._lock = threading.Lock()

    def build(self, ids: Sequence[str], vectors: np.ndarray) -> None:
        matrix = np.asarray(vectors, dtype="float32")
        with self._lock:
            self.ids = list(ids)
            self._pos = {pid: i for i, pid in enumerate(self.ids)}
            self._index = self._faiss.IndexFlatIP(self.dim)
            if matrix.size:
                self._index.add(matrix)

    def search(self, vector: np.ndarray, k: int = 10) -> list[tuple[str, float]]:
        if not self.ids:
            return []
        q = np.asarray(vector, dtype="float32").reshape(1, -1)
        k = min(k, len(self.ids))
        scores, idx = self._index.search(q, k)
        return [(self.ids[i], float(s)) for s, i in zip(scores[0], idx[0]) if i >= 0]


def build_vector_store(dim: int, backend: str = "auto") -> BaseVectorStore:
    backend = (backend or "auto").lower()
    if backend in {"auto", "faiss"}:
        try:
            store = FaissVectorStore(dim)
            log.info("Vector backend: FAISS")
            return store
        except Exception as exc:  # noqa: BLE001
            if backend == "faiss":
                log.warning("FAISS requested but unavailable (%s); using NumPy index", exc)
            else:
                log.info("FAISS unavailable (%s); using NumPy index", exc)
    log.info("Vector backend: NumPy")
    return NumpyVectorStore(dim)
