"""Agent 4 - Citation Graph Intelligence.

Computes graph metrics over the citation/similarity network: PageRank
influence, community membership and bridge (interdisciplinarity) scores.
Real citation edges are pulled from Semantic Scholar when available.
"""
from __future__ import annotations

from agents.base import AgentResult, BaseAgent


class CitationAgent(BaseAgent):
    key = "citation"
    label = "Citation Graph Intelligence"
    description = "PageRank influence, community detection and citation edges from the paper graph"

    def run(self, state: dict, ctx: dict) -> AgentResult:
        index = ctx["index"]
        sources = ctx["sources"]
        scored = state.get("scored", [])[:40]

        # enrich the graph with genuine citation edges for the strongest hits
        citation_edges = 0
        if scored and sources.online():
            for entry in scored[:3]:
                refs = sources.references_for(entry["paper_id"], limit=30)
                for title in refs:
                    target = index.resolve_title(title)
                    if target and target != entry["paper_id"]:
                        index.graph.add_edge(entry["paper_id"], target, "cites", 1.0)
                        citation_edges += 1
            if citation_edges:
                index.invalidate_analytics()
                ctx["log"](self.key, f"Added {citation_edges} real citation edges")

        analytics = index.analytics()
        influence = analytics["influence"]
        community = analytics["community"]
        labels = analytics["community_labels"]
        bridge = analytics["bridge"]
        stats = index.graph.stats()

        per_paper = {}
        for entry in scored:
            pid = entry["paper_id"]
            per_paper[pid] = {
                "influence": round(float(influence.get(pid, 0.0)), 4),
                "community": int(community.get(pid, -1)),
                "community_label": labels.get(int(community.get(pid, -1)), ""),
                "bridge": round(float(bridge.get(pid, 0.0)), 4),
            }

        bridges = sorted(per_paper.items(), key=lambda kv: -kv[1]["bridge"])[:3]
        ctx["log"](self.key, f"Graph: {stats['nodes']} nodes, {stats['edges']} edges, "
                             f"{analytics['communities']} communities")
        for pid, data in bridges:
            if data["bridge"] > 0:
                ctx["log"](self.key, f"Bridge paper detected: {pid} ({data['bridge']:.3f})")

        note = (f"{stats['nodes']} nodes · {stats['edges']} edges · "
                f"{analytics['communities']} communities")
        return AgentResult(
            update={"graph": {"stats": stats, "communities": analytics["communities"],
                              "community_labels": {str(k): v for k, v in labels.items()},
                              "per_paper": per_paper, "citation_edges": citation_edges}},
            note=note,
            metrics={"nodes": stats["nodes"], "edges": stats["edges"],
                     "communities": analytics["communities"], "citation_edges": citation_edges},
        )
