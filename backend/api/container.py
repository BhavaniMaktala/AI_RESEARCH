"""Service container: builds every backend once and hands it to the routes."""
from __future__ import annotations

import logging

from services.cache import TTLCache
from services.embeddings import build_embedder
from services.graphstore import build_graph_store
from services.index import PaperIndex
from services.llm import build_llm
from services.nlp import TextAnalyzer
from services.papersources import PaperSourceManager
from services.repository import build_repository
from services.search_service import SearchService
from services.vectorstore import build_vector_store

log = logging.getLogger(__name__)


class ServiceContainer:
    def __init__(self, config):
        self.config = config
        self.cache = TTLCache(config.CACHE_TTL)

        self.repo = build_repository(config.DB_PATH, config.MONGO_URI, config.MONGO_DB)
        self.analyzer = TextAnalyzer()
        self.embedder = build_embedder(config.EMBEDDING_PROVIDER, config.EMBEDDING_MODEL,
                                       config.EMBEDDING_DIM)
        self.vector_store = build_vector_store(self.embedder.dim, config.VECTOR_BACKEND)
        self.graph = build_graph_store(config.NEO4J_URI, config.NEO4J_USER,
                                       config.NEO4J_PASSWORD, config.GRAPH_SNAPSHOT)
        self.index = PaperIndex(config, self.repo, self.embedder, self.vector_store,
                                self.graph, self.analyzer)
        self.sources = PaperSourceManager(config, self.cache)
        self.llm = build_llm(config)
        self.search = SearchService(self)
        self._load_corpus()

    def _load_corpus(self) -> None:
        papers = list(self.sources.seed.papers)
        known = {p["paper_id"] for p in papers}
        try:
            for paper in self.repo.all_papers():
                if paper["paper_id"] not in known:
                    papers.append(paper)
                    known.add(paper["paper_id"])
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not read stored papers: %s", exc)
        self.index.build(papers)
        log.info("Index ready with %s papers", len(papers))

    def status(self) -> dict:
        return {
            "status": "ok",
            "version": "1.0.0",
            "index": self.index.stats(),
            "database": self.repo.stats(),
            "graph": self.graph.stats(),
            "sources": {
                "offline_corpus": len(self.sources.seed.papers),
                "semantic_scholar": {"enabled": self.sources.s2.enabled,
                                     "reachable": self.sources.online()},
                "arxiv": {"enabled": self.sources.arxiv.enabled},
                "mode": self.config.ONLINE_MODE,
            },
            "llm": self.llm.info(),
            "cache": self.cache.stats(),
            "weights": self.config.WEIGHTS,
        }
