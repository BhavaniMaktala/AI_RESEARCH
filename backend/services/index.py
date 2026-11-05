"""The retrieval core: one index over embeddings, BM25 and the paper graph.

Holds the canonical in-memory view of every paper the platform knows about
(seed corpus + anything fetched live + anything in the database).
"""
from __future__ import annotations

import logging
import threading
from typing import Iterable

import numpy as np

from services.lexical import BM25Index
from services.nlp import TextAnalyzer, normalize_title

log = logging.getLogger(__name__)


class PaperIndex:
    def __init__(self, config, repository, embedder, vector_store, graph_store, analyzer: TextAnalyzer):
        self.config = config
        self.repo = repository
        self.embedder = embedder
        self.vector_store = vector_store
        self.graph = graph_store
        self.analyzer = analyzer
        self.bm25 = BM25Index()

        self.papers: dict[str, dict] = {}
        self._ids: list[str] = []
        self._row: dict[str, int] = {}
        self._matrix: np.ndarray | None = None
        self._title_index: dict[str, str] = {}
        self._analytics: dict | None = None
        self._lock = threading.RLock()
        self.build_count = 0

    # ------------------------------------------------------------------ build
    def build(self, papers: Iterable[dict]) -> None:
        with self._lock:
            for paper in papers:
                self._remember(paper)
            self._rebuild()

    def add(self, papers: Iterable[dict]) -> list[dict]:
        """Add (or refresh) papers; returns only the ones that were new."""
        added: list[dict] = []
        with self._lock:
            for paper in papers:
                if not paper.get("paper_id") or not paper.get("title"):
                    continue
                if paper["paper_id"] not in self.papers:
                    added.append(paper)
                self._remember(paper)
            if added:
                self._rebuild()
        return added

    def _remember(self, paper: dict) -> None:
        pid = paper["paper_id"]
        existing = self.papers.get(pid, {})
        merged = {**existing, **paper}
        self.papers[pid] = merged
        self._title_index[normalize_title(merged.get("title", ""))] = pid
        try:
            self.repo.upsert_paper(merged)
        except Exception as exc:  # noqa: BLE001
            log.debug("Could not persist paper %s: %s", pid, exc)

    def _rebuild(self) -> None:
        self._ids = list(self.papers.keys())
        if not self._ids:
            self._matrix = None
            self._analytics = None
            return
        docs = [self._doc_text(self.papers[pid]) for pid in self._ids]

        self.analyzer.fit(docs)
        self.embedder.fit(docs)
        matrix = self.embedder.embed_documents(docs)
        self._matrix = matrix
        self._row = {pid: i for i, pid in enumerate(self._ids)}
        self.vector_store.dim = matrix.shape[1] if matrix.size else self.embedder.dim
        self.vector_store.build(self._ids, matrix)
        self.bm25.build(list(zip(self._ids, docs)))

        for pid in self._ids:
            self.graph.upsert_paper(self.papers[pid])
        self._link_graph(matrix)
        self._analytics = None
        self.build_count += 1
        log.info("Index rebuilt: %s papers, %s dims", len(self._ids), matrix.shape[1] if matrix.size else 0)

    @staticmethod
    def _doc_text(paper: dict) -> str:
        parts = [paper.get("title", ""), paper.get("abstract", "")]
        if paper.get("venue"):
            parts.append(paper["venue"])
        return " . ".join(p for p in parts if p)

    def _link_graph(self, matrix: np.ndarray) -> None:
        """k-nearest-neighbour similarity edges (weight = cosine similarity).

        Real citation edges are added later by the Citation agent when
        Semantic Scholar reference data is available.
        """
        n = matrix.shape[0]
        if n < 2:
            return
        threshold = self.config.SIMILARITY_EDGE_THRESHOLD
        k = min(self.config.SIMILARITY_KNN, n - 1)
        chunk = 256
        for start in range(0, n, chunk):
            block = matrix[start:start + chunk] @ matrix.T
            for offset in range(block.shape[0]):
                i = start + offset
                row = block[offset]
                row[i] = -1.0
                top = np.argpartition(-row, min(k, n - 1) - 1)[:k]
                for j in top:
                    score = float(row[j])
                    if score >= threshold:
                        self.graph.add_edge(self._ids[i], self._ids[j], "similar_to", score)

    # ---------------------------------------------------------------- queries
    def get(self, paper_id: str) -> dict | None:
        return self.papers.get(paper_id)

    def get_many(self, ids: Iterable[str]) -> list[dict]:
        return [self.papers[i] for i in ids if i in self.papers]

    def vector_search(self, vector: np.ndarray, k: int = 50) -> list[tuple[str, float]]:
        return self.vector_store.search(vector, k)

    def lexical_search(self, query: str, k: int = 50) -> list[tuple[str, float]]:
        return self.bm25.search(query, k)

    def embed(self, text: str) -> np.ndarray:
        return self.embedder.embed_query(text)

    def vector_of(self, paper_id: str) -> np.ndarray | None:
        idx = self._row.get(paper_id)
        if idx is None or self._matrix is None:
            return None
        return self._matrix[idx]

    def similarity(self, a: str, b: str) -> float:
        va, vb = self.vector_of(a), self.vector_of(b)
        if va is None or vb is None:
            return 0.0
        return float(np.dot(va, vb))

    def similar_to(self, paper_id: str, k: int = 8) -> list[tuple[str, float]]:
        vec = self.vector_of(paper_id)
        if vec is None:
            return []
        results = self.vector_store.search(vec, k + 1)
        return [(pid, s) for pid, s in results if pid != paper_id][:k]

    def resolve_title(self, title: str) -> str | None:
        return self._title_index.get(normalize_title(title))

    # -------------------------------------------------------------- analytics
    def analytics(self) -> dict:
        if self._analytics is not None:
            return self._analytics
        raw = self.graph.analytics()
        pagerank = raw.get("pagerank", {})
        max_pr = max(pagerank.values()) if pagerank else 1.0
        influence = {pid: (v / max_pr if max_pr else 0.0) for pid, v in pagerank.items()}

        community = raw.get("community", {})
        betweenness = raw.get("betweenness", {})
        max_bw = max(betweenness.values()) if betweenness else 1.0

        # human-readable labels for each community
        buckets: dict[int, list[str]] = {}
        for pid, cid in community.items():
            paper = self.papers.get(pid)
            if paper:
                buckets.setdefault(cid, []).append(f"{paper.get('title', '')} {paper.get('abstract', '')[:400]}")
        labels: dict[int, str] = {}
        for cid, texts in buckets.items():
            kws = self.analyzer.keywords(" ".join(texts[:40]), k=3)
            labels[cid] = " · ".join(kws) if kws else f"Cluster {cid + 1}"

        self._analytics = {
            "influence": influence,
            "community": community,
            "community_labels": labels,
            "bridge": {pid: (v / max_bw if max_bw else 0.0) for pid, v in betweenness.items()},
            "communities": raw.get("communities", 0),
        }
        return self._analytics

    def invalidate_analytics(self) -> None:
        """Drop cached graph analytics (call after adding citation edges)."""
        self._analytics = None

    def influence_of(self, paper_id: str) -> float:
        return float(self.analytics()["influence"].get(paper_id, 0.0))

    # ------------------------------------------------------------------ stats
    def stats(self) -> dict:
        return {
            "papers_indexed": len(self.papers),
            "vectors": len(self.vector_store),
            "embedding": self.embedder.info(),
            "vector_backend": self.vector_store.info(),
            "graph": self.graph.stats(),
            "communities": self.analytics().get("communities", 0) if self.papers else 0,
            "index_builds": self.build_count,
        }
