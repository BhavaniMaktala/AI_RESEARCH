"""Citation / similarity graph store.

Neo4j is used when NEO4J_URI is configured (persistent, Cypher-queried).
Otherwise an in-process NetworkX graph is used, which is enough for the
bundled corpus and keeps the app zero-setup.

Analytics (PageRank influence, community detection, bridge scores) run on a
NetworkX projection of the graph in both cases, so results are identical.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Iterable

import networkx as nx

log = logging.getLogger(__name__)


class BaseGraphStore:
    kind = "base"

    def upsert_paper(self, paper: dict) -> None:
        raise NotImplementedError

    def add_edge(self, source: str, target: str, kind: str = "similar_to", weight: float = 1.0) -> None:
        raise NotImplementedError

    def neighbors(self, paper_id: str, depth: int = 1, limit: int = 60) -> dict:
        raise NotImplementedError

    def subgraph(self, ids: Iterable[str]) -> dict:
        raise NotImplementedError

    def stats(self) -> dict:
        raise NotImplementedError

    # -- shared helpers ---------------------------------------------------
    @staticmethod
    def _serialise(graph: nx.Graph, ids: set[str] | None = None) -> dict:
        nodes = [
            {"id": n, **{k: v for k, v in d.items() if k != "abstract"}}
            for n, d in graph.nodes(data=True)
            if ids is None or n in ids
        ]
        keep = {n["id"] for n in nodes}
        edges = [
            {"source": u, "target": v, "kind": d.get("kind", "similar_to"), "weight": round(float(d.get("weight", 1.0)), 4)}
            for u, v, d in graph.edges(data=True)
            if u in keep and v in keep
        ]
        return {"nodes": nodes, "edges": edges}


class NetworkXGraphStore(BaseGraphStore):
    kind = "networkx"

    def __init__(self, snapshot_path: str | None = None):
        self.graph = nx.Graph()
        self.snapshot_path = snapshot_path
        self._lock = threading.RLock()
        self._analytics_cache: dict[str, Any] | None = None
        self._analytics_key: tuple | None = None
        if snapshot_path and os.path.exists(snapshot_path):
            self._load_snapshot()

    # -- writes -----------------------------------------------------------
    def upsert_paper(self, paper: dict) -> None:
        attrs = {
            "title": paper.get("title", "")[:300],
            "year": paper.get("year"),
            "venue": paper.get("venue", ""),
            "source": paper.get("source", ""),
            "categories": paper.get("categories", [])[:4],
            "citation_count": paper.get("citation_count") or 0,
        }
        with self._lock:
            if self.graph.has_node(paper["paper_id"]):
                self.graph.nodes[paper["paper_id"]].update(attrs)
            else:
                self.graph.add_node(paper["paper_id"], **attrs)
            self._invalidate()

    def add_edge(self, source: str, target: str, kind: str = "similar_to", weight: float = 1.0) -> None:
        if not source or not target or source == target:
            return
        with self._lock:
            if not (self.graph.has_node(source) and self.graph.has_node(target)):
                return
            if self.graph.has_edge(source, target):
                data = self.graph[source][target]
                if weight > data.get("weight", 0):
                    data["weight"] = weight
                    data["kind"] = kind
            else:
                self.graph.add_edge(source, target, kind=kind, weight=float(weight))
            self._invalidate()

    # -- reads ------------------------------------------------------------
    def neighbors(self, paper_id: str, depth: int = 1, limit: int = 60) -> dict:
        with self._lock:
            if not self.graph.has_node(paper_id):
                return {"nodes": [], "edges": [], "center": paper_id}
            nodes = nx.single_source_shortest_path_length(self.graph, paper_id, cutoff=max(1, depth))
            ids = set(list(nodes)[:limit])
            sub = self.graph.subgraph(ids)
            payload = self._serialise(sub)
            payload["center"] = paper_id
            return payload

    def subgraph(self, ids: Iterable[str]) -> dict:
        ids = [i for i in ids if self.graph.has_node(i)]
        with self._lock:
            return self._serialise(self.graph.subgraph(ids))

    def stats(self) -> dict:
        with self._lock:
            return {
                "backend": self.kind,
                "nodes": self.graph.number_of_nodes(),
                "edges": self.graph.number_of_edges(),
                "density": round(nx.density(self.graph), 6) if self.graph.number_of_nodes() > 1 else 0.0,
            }

    # -- analytics --------------------------------------------------------
    def _invalidate(self) -> None:
        self._analytics_cache = None

    def analytics(self) -> dict:
        with self._lock:
            key = (self.graph.number_of_nodes(), self.graph.number_of_edges())
            if self._analytics_cache is not None and self._analytics_key == key:
                return self._analytics_cache
            g = self.graph
            if g.number_of_nodes() == 0:
                result = {"pagerank": {}, "community": {}, "betweenness": {}, "communities": 0}
                self._analytics_cache, self._analytics_key = result, key
                return result

            pagerank = nx.pagerank(g, weight="weight", alpha=0.85)
            try:
                communities = list(nx.community.greedy_modularity_communities(g, weight="weight"))
            except Exception:  # noqa: BLE001 - tiny/degenerate graphs
                communities = [set(g.nodes())]
            community_map = {n: ci for ci, members in enumerate(communities) for n in members}
            betweenness = nx.betweenness_centrality(g, weight=None, normalized=True) if g.number_of_nodes() <= 800 else {}

            result = {
                "pagerank": pagerank,
                "community": community_map,
                "betweenness": betweenness,
                "communities": len(communities),
            }
            self._analytics_cache, self._analytics_key = result, key
            return result

    # -- persistence ------------------------------------------------------
    def persist(self) -> None:
        if not self.snapshot_path:
            return
        with self._lock:
            payload = nx.node_link_data(self.graph, edges="edges")
        os.makedirs(os.path.dirname(self.snapshot_path), exist_ok=True)
        tmp = self.snapshot_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp, self.snapshot_path)

    def _load_snapshot(self) -> None:
        try:
            with open(self.snapshot_path, encoding="utf-8") as fh:
                payload = json.load(fh)
            self.graph = nx.node_link_graph(payload, edges="edges")
            log.info("Loaded graph snapshot: %s nodes", self.graph.number_of_nodes())
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not load graph snapshot (%s); starting empty", exc)


class Neo4jGraphStore(BaseGraphStore):
    """Persists nodes/edges in Neo4j; analytics use a NetworkX projection."""

    kind = "neo4j"

    def __init__(self, uri: str, user: str, password: str):
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._driver.verify_connectivity()
        self._lock = threading.RLock()
        self._projection: nx.Graph | None = None
        with self._driver.session() as s:
            s.run("CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.paper_id IS UNIQUE")

    def upsert_paper(self, paper: dict) -> None:
        with self._driver.session() as s:
            s.run(
                """
                MERGE (p:Paper {paper_id: $paper_id})
                SET p.title = $title, p.year = $year, p.venue = $venue,
                    p.source = $source, p.categories = $categories,
                    p.citation_count = $citation_count
                """,
                paper_id=paper["paper_id"], title=(paper.get("title") or "")[:300],
                year=paper.get("year"), venue=paper.get("venue", ""),
                source=paper.get("source", ""), categories=paper.get("categories", [])[:4],
                citation_count=paper.get("citation_count") or 0,
            )
        self._projection = None

    def add_edge(self, source: str, target: str, kind: str = "similar_to", weight: float = 1.0) -> None:
        if source == target:
            return
        rel = "CITES" if kind == "cites" else "SIMILAR_TO"
        with self._driver.session() as s:
            s.run(
                f"""
                MATCH (a:Paper {{paper_id: $src}}), (b:Paper {{paper_id: $dst}})
                MERGE (a)-[r:{rel}]->(b)
                SET r.weight = $weight
                """,
                src=source, dst=target, weight=float(weight),
            )
        self._projection = None

    def _graph(self) -> nx.Graph:
        if self._projection is not None:
            return self._projection
        g = nx.Graph()
        with self._driver.session() as s:
            for rec in s.run("MATCH (p:Paper) RETURN p"):
                p = dict(rec["p"])
                g.add_node(p["paper_id"], **{k: v for k, v in p.items() if k != "paper_id"})
            for rec in s.run("MATCH (a:Paper)-[r]->(b:Paper) RETURN a.paper_id AS s, b.paper_id AS t, type(r) AS k, r.weight AS w"):
                if g.has_node(rec["s"]) and g.has_node(rec["t"]):
                    g.add_edge(rec["s"], rec["t"], kind="cites" if rec["k"] == "CITES" else "similar_to",
                               weight=float(rec["w"] or 1.0))
        self._projection = g
        return g

    def neighbors(self, paper_id: str, depth: int = 1, limit: int = 60) -> dict:
        g = self._graph()
        if not g.has_node(paper_id):
            return {"nodes": [], "edges": [], "center": paper_id}
        nodes = nx.single_source_shortest_path_length(g, paper_id, cutoff=max(1, depth))
        ids = set(list(nodes)[:limit])
        payload = self._serialise(g.subgraph(ids))
        payload["center"] = paper_id
        return payload

    def subgraph(self, ids: Iterable[str]) -> dict:
        g = self._graph()
        ids = [i for i in ids if g.has_node(i)]
        return self._serialise(g.subgraph(ids))

    def stats(self) -> dict:
        g = self._graph()
        return {"backend": self.kind, "nodes": g.number_of_nodes(), "edges": g.number_of_edges(),
                "density": round(nx.density(g), 6) if g.number_of_nodes() > 1 else 0.0}

    def analytics(self) -> dict:
        g = self._graph()
        if g.number_of_nodes() == 0:
            return {"pagerank": {}, "community": {}, "betweenness": {}, "communities": 0}
        pagerank = nx.pagerank(g, weight="weight")
        try:
            communities = list(nx.community.greedy_modularity_communities(g, weight="weight"))
        except Exception:  # noqa: BLE001
            communities = [set(g.nodes())]
        community_map = {n: ci for ci, members in enumerate(communities) for n in members}
        betweenness = nx.betweenness_centrality(g, normalized=True) if g.number_of_nodes() <= 800 else {}
        return {"pagerank": pagerank, "community": community_map,
                "betweenness": betweenness, "communities": len(communities)}

    def persist(self) -> None:
        return None


def build_graph_store(uri: str = "", user: str = "", password: str = "", snapshot_path: str | None = None) -> BaseGraphStore:
    if uri and password:
        try:
            store = Neo4jGraphStore(uri, user or "neo4j", password)
            log.info("Graph backend: Neo4j (%s)", uri)
            return store
        except Exception as exc:  # noqa: BLE001
            log.warning("Neo4j unavailable (%s); using in-process NetworkX graph", exc)
    log.info("Graph backend: NetworkX (in-process)")
    return NetworkXGraphStore(snapshot_path)
