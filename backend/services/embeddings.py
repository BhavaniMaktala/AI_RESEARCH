"""Embedding providers.

Priority:
1. sentence-transformers (real transformer embeddings, ~90 MB model)
2. TF-IDF + Truncated SVD (fully offline, no model download)

Both expose the same interface and return L2-normalised vectors, so the
vector store, ranking and personalisation code is provider-agnostic.
"""
from __future__ import annotations

import logging
import threading
from typing import Sequence

import numpy as np

log = logging.getLogger(__name__)


def _l2(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class BaseEmbedder:
    name = "base"
    kind = "base"
    dim = 384
    fitted = True

    def fit(self, texts: Sequence[str]) -> None:  # noqa: D401 - no-op by default
        return None

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        raise NotImplementedError

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]

    def info(self) -> dict:
        return {"name": self.name, "kind": self.kind, "dim": self.dim}


class SentenceTransformerEmbedder(BaseEmbedder):
    """Transformer sentence embeddings (all-MiniLM-L6-v2 by default)."""

    kind = "sentence-transformers"

    def __init__(self, model_name: str, dim: int = 384):
        from sentence_transformers import SentenceTransformer  # lazy heavy import

        self.name = model_name
        self.dim = dim
        self._model = SentenceTransformer(model_name)
        try:
            self.dim = int(self._model.get_sentence_embedding_dimension())
        except Exception:  # pragma: no cover
            pass

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype="float32")
        vecs = self._model.encode(
            list(texts), batch_size=32, convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False,
        )
        return np.asarray(vecs, dtype="float32")


class TfidfSvdEmbedder(BaseEmbedder):
    """Offline semantic embedding: TF-IDF -> latent semantic analysis (SVD).

    Cheap, deterministic, needs no model download, and still captures
    synonym-ish co-occurrence structure well enough for retrieval over a
    few thousand abstracts.
    """

    kind = "tfidf-svd"

    def __init__(self, dim: int = 384):
        self.name = f"tfidf-svd-{dim}"
        self.dim = dim
        self.fitted = False
        self._lock = threading.Lock()

    def fit(self, texts: Sequence[str]) -> None:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        texts = [t or "" for t in texts]
        if not texts:
            return
        with self._lock:
            self._vectorizer = TfidfVectorizer(
                stop_words="english", ngram_range=(1, 2), min_df=1,
                max_features=60000, sublinear_tf=True, strip_accents="unicode",
            )
            matrix = self._vectorizer.fit_transform(texts)
            n_components = max(2, min(self.dim, matrix.shape[1] - 1, matrix.shape[0] - 1))
            self._svd = TruncatedSVD(n_components=n_components, random_state=42)
            self._svd.fit(matrix)
            self.dim = int(n_components)
            self.name = f"tfidf-svd-{self.dim}"
            self.fitted = True
            log.info("TF-IDF/SVD embedder fitted: %s docs, %s dims", len(texts), self.dim)

    def _ensure_fitted(self, texts: Sequence[str]) -> None:
        if not self.fitted:
            self.fit(texts)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        texts = [t or "" for t in texts]
        self._ensure_fitted(texts)
        if not texts:
            return np.zeros((0, self.dim), dtype="float32")
        matrix = self._vectorizer.transform(texts)
        vecs = self._svd.transform(matrix).astype("float32")
        return _l2(vecs)


def build_embedder(provider: str = "auto", model: str = "", dim: int = 384) -> BaseEmbedder:
    provider = (provider or "auto").lower()
    if provider in {"auto", "sentence-transformers", "st"}:
        try:
            emb = SentenceTransformerEmbedder(model or "sentence-transformers/all-MiniLM-L6-v2", dim)
            log.info("Embedding provider: sentence-transformers (%s)", emb.name)
            return emb
        except Exception as exc:  # noqa: BLE001 - any failure means fallback
            if provider in {"sentence-transformers", "st"}:
                log.warning("sentence-transformers requested but unavailable (%s); using TF-IDF/SVD", exc)
            else:
                log.info("sentence-transformers not installed - using TF-IDF + SVD "
                         "(optional: pip install sentence-transformers for stronger semantic matching)")
    log.info("Embedding provider: TF-IDF + SVD")
    return TfidfSvdEmbedder(dim)
