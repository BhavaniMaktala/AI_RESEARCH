"""Dashboard analytics endpoint."""
from __future__ import annotations

from flask import Blueprint, jsonify

from api.deps import container

bp = Blueprint("insights", __name__, url_prefix="/api")


@bp.get("/insights")
def insights():
    c = container()
    data = c.repo.insights()
    analytics = c.index.analytics()
    top = sorted(analytics["influence"].items(), key=lambda kv: -kv[1])[:6]
    data["system"] = {
        "papers_indexed": len(c.index.papers),
        "graph": c.graph.stats(),
        "communities": analytics["communities"],
        "embedding": c.embedder.info(),
        "vector_backend": c.vector_store.info(),
        "database": c.repo.stats(),
        "llm": c.llm.info(),
    }
    data["top_influence"] = [
        {"paper_id": pid, "title": c.index.papers.get(pid, {}).get("title", pid),
         "influence": round(score, 4),
         "community_label": analytics["community_labels"].get(
             int(analytics["community"].get(pid, -1)), "")}
        for pid, score in top
    ]
    return jsonify(data)
