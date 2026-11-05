"""Citation / similarity graph endpoints for the graph explorer."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from api.deps import container, parse_int

bp = Blueprint("graph", __name__, url_prefix="/api/graph")


@bp.get("/overview")
def overview():
    limit = parse_int(request.args.get("limit"), 120) or 120
    community = parse_int(request.args.get("community"), None)
    return jsonify(container().search.graph_overview(limit=min(limit, 400), community=community))


@bp.get("/stats")
def stats():
    index = container().index
    analytics = index.analytics()
    return jsonify({
        "graph": index.graph.stats(),
        "communities": analytics["communities"],
        "labels": analytics["community_labels"],
        "top_influence": sorted(
            ({"paper_id": pid, "title": index.papers.get(pid, {}).get("title", pid),
              "influence": round(score, 4)}
             for pid, score in analytics["influence"].items()),
            key=lambda x: -x["influence"])[:10],
    })
