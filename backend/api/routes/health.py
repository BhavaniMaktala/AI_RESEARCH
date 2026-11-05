"""Health, capability and agent-registry endpoints."""
from __future__ import annotations

from flask import Blueprint, jsonify

from agents.orchestrator import build_orchestrator
from api.deps import container

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    c = container()
    return jsonify({
        "status": "ok",
        "papers_indexed": len(c.index.papers),
        "graph": c.graph.stats(),
        "embedding": c.embedder.kind,
        "vector_backend": c.vector_store.backend,
        "database": c.repo.kind,
    })


@bp.get("/config")
def config_status():
    return jsonify(container().status())


@bp.get("/agents")
def agents():
    orchestrator = build_orchestrator()
    return jsonify({"agents": orchestrator.describe(), "count": len(orchestrator.agents)})
